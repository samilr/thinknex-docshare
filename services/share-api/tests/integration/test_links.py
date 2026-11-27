"""Enlaces de ThinkNex Docs (canal LINK), audiencia y permisos Ver / Descargar / Editar."""

import pytest

from tests.helpers import make_pdf
from tests.integration.conftest import ACCESS, Api

pytestmark = pytest.mark.integration

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _token(share: dict[str, object]) -> str:
    link = share["link"]
    assert isinstance(link, str) and "/s/" in link
    return link.rsplit("/s/", 1)[1]


def _anyone_view(api: Api, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "channel": "LINK",
        "audience": "ANYONE",
        "permission": "VIEW",
        "recipient": None,
        "reason": "Folleto para quien lo pida",
    }
    body.update(overrides)
    return api.share(**body)


def test_anyone_view_link(api: Api) -> None:
    share = _anyone_view(api)
    assert share["channel"] == "LINK"
    assert share["recipient"] is None
    assert share["notification_status"] is None, "el canal LINK no envía notificaciones"
    token = _token(share)

    info = api.client.get(f"{ACCESS}/{token}").json()
    assert info["requires_code"] is False and info["destination"] is None
    assert info["document_title"] == "Documento doc-public"
    assert info["permission"] == "VIEW"
    assert api.client.post(f"{ACCESS}/{token}/otp").status_code == 409

    auth = {"Authorization": f"Bearer {api.open_link(token)}"}
    view = api.client.get(f"{ACCESS}/{token}/document", headers=auth).json()
    assert view["can_download"] is False and view["can_edit"] is False
    assert view["page_count"] == 1 and view["kind"] == "pdf"
    assert view["viewer_label"] == "Enlace público"

    page = api.client.get(f"{ACCESS}/{token}/pages/1", headers=auth)
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"
    assert page.headers["cache-control"] == "no-store"
    assert page.content.startswith(PNG_MAGIC)
    assert api.client.get(f"{ACCESS}/{token}/pages/2", headers=auth).status_code == 422

    download = api.client.get(f"{ACCESS}/{token}/download", headers=auth)
    assert download.status_code == 403
    upload = api.client.post(
        f"{ACCESS}/{token}/versions",
        headers=auth,
        files={"file": ("x.pdf", make_pdf("x"), "application/pdf")},
    )
    assert upload.status_code == 403

    events = [e["event_type"] for e in api.audit(share_id=str(share["id"]))]
    assert events[:5] == [
        "ACCESS_DENIED",
        "ACCESS_DENIED",
        "DOCUMENT_VIEWED",
        "ACCESS_GRANTED",
        "LINK_OPENED",
    ]
    assert "NOTIFICATION_SENT" not in events


def test_anyone_requires_clean_document(api: Api) -> None:
    body = {
        "document_id": "doc-pii",
        "channel": "LINK",
        "audience": "ANYONE",
        "permission": "VIEW",
        "recipient": None,
        "reason": "intento",
        "acknowledge_sensitive": True,
    }
    r = api.client.post("/api/v1/shares", json=body, headers=api.headers("ana@thinknex.example"))
    assert r.status_code == 403, r.text
    pre = api.client.post(
        "/api/v1/shares/precheck",
        json={"document_id": "doc-pii", "audience": "ANYONE"},
        headers=api.headers("ana@thinknex.example"),
    )
    assert pre.status_code == 200
    assert pre.json()["report"]["decision"] == "BLOCK"


def test_anyone_cannot_edit_and_requires_link_channel(api: Api) -> None:
    headers = api.headers("ana@thinknex.example")
    base = {"document_id": "doc-public", "reason": "x", "recipient": None}
    r = api.client.post(
        "/api/v1/shares",
        json={**base, "channel": "LINK", "audience": "ANYONE", "permission": "EDIT"},
        headers=headers,
    )
    assert r.status_code == 422
    r = api.client.post(
        "/api/v1/shares", json={**base, "channel": "EMAIL", "audience": "ANYONE"}, headers=headers
    )
    assert r.status_code == 422
    r = api.client.post(
        "/api/v1/shares", json={**base, "channel": "LINK", "audience": "SPECIFIC"}, headers=headers
    )
    assert r.status_code == 422, "una persona específica necesita destinatario"


def test_link_for_specific_person_sends_code_by_email(api: Api) -> None:
    share = api.share(
        channel="LINK",
        permission="VIEW",
        recipient={"name": "Lucía Socia", "email": "lucia@socio.example"},
    )
    assert share["audience"] == "SPECIFIC"
    token = _token(share)
    info = api.client.get(f"{ACCESS}/{token}").json()
    assert info["requires_code"] is True and info["document_title"] is None
    assert api.client.post(f"{ACCESS}/{token}/open").status_code == 409
    access = api.unlock(token)
    otp = api.last_message("OTP")
    assert otp["channel"] == "EMAIL" and otp["to"] == "lucia@socio.example"
    view = api.client.get(
        f"{ACCESS}/{token}/document", headers={"Authorization": f"Bearer {access}"}
    ).json()
    assert view["viewer_label"] == "Lucía Socia"


def test_edit_works_on_live_file(api: Api) -> None:
    source = api.components.source
    before = source.get_metadata("doc-edit").version  # type: ignore[attr-defined]
    share = api.share(
        document_id="doc-edit",
        channel="EMAIL",
        permission="EDIT",
        recipient={"name": "Rocío Editora", "email": "rocio@socio.example"},
    )
    token = api.last_link_token()
    assert "publicar nuevas versiones" in api.last_message("LINK")["body"]
    auth = {"Authorization": f"Bearer {api.unlock(token)}"}

    view = api.client.get(f"{ACCESS}/{token}/document", headers=auth).json()
    assert view["can_edit"] is True and view["live"] is True and view["version"] == before

    upload = api.client.post(
        f"{ACCESS}/{token}/versions",
        headers=auth,
        files={"file": ("propuesta.pdf", make_pdf("Propuesta revisada"), "application/pdf")},
        data={"comment": "Ajustes del socio"},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["version"] == before + 1
    versions = source.versions("doc-edit")  # type: ignore[attr-defined]
    assert versions[0].created_by == "destinatario:rocio@socio.example"

    # El visor muestra ahora la versión nueva (archivo vivo).
    view = api.client.get(f"{ACCESS}/{token}/document", headers=auth).json()
    assert view["version"] == before + 1

    uploaded = api.audit(share_id=str(share["id"]), event_type="DOCUMENT_VERSION_UPLOADED")
    assert uploaded[0]["actor_type"] == "RECIPIENT"
    assert uploaded[0]["metadata"]["version"] == before + 1  # type: ignore[index]
    verify = api.client.get("/api/v1/audit/verify", headers=api.headers("carla@thinknex.example"))
    assert verify.json()["valid"] is True


def test_rotating_link_invalidates_previous(api: Api) -> None:
    share = _anyone_view(api, document_id="doc-rotate")
    old = _token(share)
    url = f"/api/v1/shares/{share['id']}/link"
    assert api.client.post(url, headers=api.headers("bruno@thinknex.example")).status_code == 404
    r = api.client.post(url, headers=api.headers("ana@thinknex.example"))
    assert r.status_code == 200, r.text
    new = _token(r.json())
    assert new != old
    assert api.client.get(f"{ACCESS}/{old}").status_code == 404
    assert api.client.get(f"{ACCESS}/{new}").status_code == 200
    events = [e["event_type"] for e in api.audit(share_id=str(share["id"]))]
    assert "SHARE_LINK_ROTATED" in events

    email_share = api.share()
    r = api.client.post(
        f"/api/v1/shares/{email_share['id']}/link", headers=api.headers("ana@thinknex.example")
    )
    assert r.status_code == 409, "solo los envíos por enlace de ThinkNex Docs se regeneran"


def test_anyone_link_session_limit(api: Api) -> None:
    share = _anyone_view(api, max_accesses=2)
    token = _token(share)
    first = api.open_link(token)
    api.open_link(token)
    assert api.client.post(f"{ACCESS}/{token}/open").status_code == 404
    still = api.client.get(
        f"{ACCESS}/{token}/document", headers={"Authorization": f"Bearer {first}"}
    )
    assert still.status_code == 200, "las sesiones iniciadas siguen vigentes"


def test_session_is_bound_to_its_share(api: Api) -> None:
    a = _token(_anyone_view(api))
    b = _token(_anyone_view(api))
    access_a = api.open_link(a)
    r = api.client.get(f"{ACCESS}/{b}/document", headers={"Authorization": f"Bearer {access_a}"})
    assert r.status_code == 404


def test_owner_edits_access_and_it_applies_immediately(api: Api) -> None:
    share = api.share(max_accesses=1)
    token = api.last_link_token()
    auth = {"Authorization": f"Bearer {api.unlock(token)}"}
    assert api.client.get(f"{ACCESS}/{token}/download", headers=auth).status_code == 200
    url = f"/api/v1/shares/{share['id']}"
    ana = api.headers("ana@thinknex.example")

    r = api.client.patch(url, json={"permission": "VIEW"}, headers=ana)
    assert r.status_code == 200, r.text
    assert r.json()["permission"] == "VIEW"
    # La sesión ya abierta del destinatario pierde la descarga de inmediato.
    assert api.client.get(f"{ACCESS}/{token}/download", headers=auth).status_code == 403
    assert api.client.get(f"{ACCESS}/{token}/pages/1", headers=auth).status_code == 200

    # Agotado (1 de 1): subir el máximo lo reactiva; bajarlo bajo lo usado no se permite.
    detail = api.client.get(url, headers=ana).json()
    assert detail["status"] == "EXHAUSTED"
    assert api.client.patch(url, json={"max_accesses": 0}, headers=ana).status_code == 422
    r = api.client.patch(url, json={"max_accesses": 3, "expires_in_hours": 24}, headers=ana)
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"

    updated = api.audit(share_id=str(share["id"]), event_type="SHARE_UPDATED")
    first = updated[-1]["metadata"]
    assert first["changed"] == ["permission"]  # type: ignore[index]
    assert first["before"]["permission"] == "DOWNLOAD"  # type: ignore[index]
    assert first["after"]["permission"] == "VIEW"  # type: ignore[index]
    assert set(updated[0]["metadata"]["changed"]) == {"expires_at", "max_accesses"}  # type: ignore[index]


def test_edit_access_rules(api: Api) -> None:
    anyone = _anyone_view(api, document_id="doc-rotate")
    ana = api.headers("ana@thinknex.example")
    url = f"/api/v1/shares/{anyone['id']}"
    assert api.client.patch(url, json={"permission": "EDIT"}, headers=ana).status_code == 422
    assert api.client.patch(url, json={"permission": "DOWNLOAD"}, headers=ana).status_code == 200
    bruno = api.headers("bruno@thinknex.example")
    assert api.client.patch(url, json={"permission": "VIEW"}, headers=bruno).status_code == 404
    carla = api.headers("carla@thinknex.example")
    assert api.client.patch(url, json={"permission": "VIEW"}, headers=carla).status_code == 403
    admin = api.admin_headers()
    assert api.client.patch(url, json={"permission": "VIEW"}, headers=admin).status_code == 200
    api.client.post(f"{url}/revoke", headers=ana)
    assert api.client.patch(url, json={"permission": "DOWNLOAD"}, headers=ana).status_code == 409


def test_share_without_watermark(api: Api) -> None:
    import io

    from pypdf import PdfReader

    share = api.share(watermark=False)
    assert share["watermark"] is False
    token = api.last_link_token()
    auth = {"Authorization": f"Bearer {api.unlock(token)}"}
    view = api.client.get(f"{ACCESS}/{token}/document", headers=auth).json()
    assert view["watermark"] is False
    pdf = api.client.get(f"{ACCESS}/{token}/download", headers=auth)
    text = PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert "Compartido con" not in text
    accessed = api.audit(share_id=str(share["id"]), event_type="DOCUMENT_ACCESSED")[0]
    assert accessed["metadata"]["watermarked"] is False  # type: ignore[index]

    ana = api.headers("ana@thinknex.example")
    r = api.client.patch(f"/api/v1/shares/{share['id']}", json={"watermark": True}, headers=ana)
    assert r.json()["watermark"] is True
    pdf = api.client.get(f"{ACCESS}/{token}/download", headers=auth)
    assert "Compartido con" in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()


def test_owner_can_see_link_again(api: Api) -> None:
    link_share = _anyone_view(api)
    ana = api.headers("ana@thinknex.example")
    url = f"/api/v1/shares/{link_share['id']}/link"
    r = api.client.get(url, headers=ana)
    assert r.status_code == 200 and r.json()["link"] == link_share["link"]
    assert api.client.get(url, headers=api.admin_headers()).json()["link"] == link_share["link"]
    assert api.client.get(url, headers=api.headers("bruno@thinknex.example")).status_code == 404
    assert api.client.get(url, headers=api.headers("carla@thinknex.example")).status_code == 403
    viewed = api.audit(share_id=str(link_share["id"]), event_type="SHARE_LINK_VIEWED")
    assert len(viewed) == 2

    email_share = api.share()
    token = api.last_link_token()
    r = api.client.get(f"/api/v1/shares/{email_share['id']}/link", headers=ana)
    assert r.json()["link"].endswith(f"/s/{token}")

    # Tras regenerar, se muestra el enlace nuevo; tras revocar, ya no.
    rotated = api.client.post(url, headers=ana).json()["link"]
    assert api.client.get(url, headers=ana).json()["link"] == rotated
    api.client.post(f"/api/v1/shares/{link_share['id']}/revoke", headers=ana)
    assert api.client.get(url, headers=ana).status_code == 409
