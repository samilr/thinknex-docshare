"""Política configurable por el ADMIN y administración de archivos de la biblioteca."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.integration.conftest import Api

pytestmark = pytest.mark.integration
POLICIES = "/api/v1/admin/policies"
EXTERNAL = {"name": "Juan", "email": "juan@cliente.example"}


def _rule(api: Api, name: str) -> dict[str, Any]:
    rules = api.client.get(POLICIES, headers=api.admin_headers()).json()
    return next(r for r in rules if r["name"] == name)


def _body(rule: dict[str, Any], **changes: Any) -> dict[str, Any]:
    keys = (
        "name",
        "description",
        "action",
        "message",
        "classifications",
        "recipient",
        "finding_types",
        "channels",
        "audiences",
        "enabled",
    )
    return {**{k: rule[k] for k in keys}, **changes}


def _precheck(api: Api, document_id: str, **extra: Any) -> dict[str, Any]:
    r = api.client.post(
        "/api/v1/shares/precheck",
        json={"document_id": document_id, "recipient": EXTERNAL, **extra},
        headers=api.headers("ana@thinknex.example"),
    )
    assert r.status_code == 200, r.text
    report: dict[str, Any] = r.json()["report"]
    return report


@pytest.fixture
def personal_data_rule(api: Api) -> Iterator[dict[str, Any]]:
    """Devuelve la regla por defecto y la restaura al terminar (la BD es compartida)."""
    rule = _rule(api, "Datos personales a externos")
    yield rule
    api.client.put(f"{POLICIES}/{rule['id']}", json=_body(rule), headers=api.admin_headers())


def test_default_rules_and_who_can_see_them(api: Api) -> None:
    names = {r["name"] for r in api.client.get(POLICIES, headers=api.admin_headers()).json()}
    assert {
        "Restringidos fuera de la organización",
        "Restringidos entre áreas",
        "Confidenciales a externos",
        "Datos personales a externos",
    } <= names
    carla = api.headers("carla@thinknex.example")
    assert api.client.get(POLICIES, headers=carla).status_code == 200, "el auditor puede leer"
    ana = api.headers("ana@thinknex.example")
    assert api.client.get(POLICIES, headers=ana).status_code == 403
    rule = _rule(api, "Confidenciales a externos")
    assert (
        api.client.put(f"{POLICIES}/{rule['id']}", json=_body(rule), headers=carla).status_code
        == 403
    )


def test_admin_relaxes_email_rule(api: Api, personal_data_rule: dict[str, Any]) -> None:
    before = _precheck(api, "doc-email")
    assert before["decision"] == "WARN"
    assert "Datos personales a externos" in before["matched_rules"]

    relaxed = [t for t in personal_data_rule["finding_types"] if t != "EMAIL"]
    r = api.client.put(
        f"{POLICIES}/{personal_data_rule['id']}",
        json=_body(personal_data_rule, finding_types=relaxed),
        headers=api.admin_headers(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated_by"] == "admin@thinknex.example"
    assert _precheck(api, "doc-email")["decision"] == "ALLOW"
    # Un documento con RUT sigue requiriendo confirmación.
    assert _precheck(api, "doc-pii")["decision"] == "WARN"

    updated = api.audit(event_type="POLICY_UPDATED")[0]
    assert updated["actor"].startswith("Administrador")  # type: ignore[union-attr]
    assert updated["metadata"]["changed"] == ["finding_types"]  # type: ignore[index]
    assert "EMAIL" in updated["metadata"]["before"]["finding_types"]  # type: ignore[index]
    assert "EMAIL" not in updated["metadata"]["after"]["finding_types"]  # type: ignore[index]


def test_disabling_a_rule(api: Api, personal_data_rule: dict[str, Any]) -> None:
    api.client.put(
        f"{POLICIES}/{personal_data_rule['id']}",
        json=_body(personal_data_rule, enabled=False),
        headers=api.admin_headers(),
    )
    assert _precheck(api, "doc-pii")["decision"] == "ALLOW"


def test_create_channel_rule_then_delete(api: Api) -> None:
    admin = api.admin_headers()
    body = {
        "name": "Confidenciales nunca por WhatsApp",
        "action": "BLOCK",
        "message": "Los documentos confidenciales no se envían por WhatsApp.",
        "classifications": ["CONFIDENTIAL"],
        "channels": ["WHATSAPP"],
    }
    created = api.client.post(POLICIES, json=body, headers=admin)
    assert created.status_code == 201, created.text
    rule_id = created.json()["id"]
    assert api.client.post(POLICIES, json=body, headers=admin).status_code == 409
    assert (
        api.client.post(
            POLICIES, json=body, headers=api.headers("ana@thinknex.example")
        ).status_code
        == 403
    )
    try:
        share = {
            "document_id": "doc-confidential",
            "recipient": {"name": "Ext", "phone": "+56 9 1111 2222"},
            "channel": "WHATSAPP",
            "reason": "Contrato",
            "acknowledge_sensitive": True,
        }
        ana = api.headers("ana@thinknex.example")
        blocked = api.client.post("/api/v1/shares", json=share, headers=ana)
        assert blocked.status_code == 403
        assert "WhatsApp" in " ".join(blocked.json()["report"]["reasons"])
        by_email = {**share, "channel": "EMAIL", "recipient": EXTERNAL}
        assert api.client.post("/api/v1/shares", json=by_email, headers=ana).status_code == 201
    finally:
        assert api.client.delete(f"{POLICIES}/{rule_id}", headers=admin).status_code == 204
    deleted = api.audit(event_type="POLICY_DELETED")[0]
    assert deleted["metadata"]["before"]["action"] == "BLOCK"  # type: ignore[index]
    assert api.audit(event_type="POLICY_CREATED")[0]["metadata"]["policy_id"] == rule_id  # type: ignore[index]


def test_admin_manages_library_files(api: Api) -> None:
    admin = api.admin_headers()
    items = api.client.get(
        "/api/v1/library/items", params={"library_id": "operaciones"}, headers=admin
    )
    assert items.status_code == 200, "el ADMIN ve la biblioteca"

    url = "/api/v1/library/documents/doc-delete"
    ana = api.headers("ana@thinknex.example")
    assert (
        api.client.patch(url, json={"classification": "CONFIDENTIAL"}, headers=ana).status_code
        == 403
    ), "solo un ADMIN reclasifica"
    r = api.client.patch(url, json={"classification": "CONFIDENTIAL"}, headers=admin)
    assert r.status_code == 200 and r.json()["classification"] == "CONFIDENTIAL"
    event = api.audit(event_type="DOCUMENT_RECLASSIFIED")[0]
    assert event["metadata"]["from_classification"] == "INTERNAL"  # type: ignore[index]

    share = api.share(document_id="doc-delete", acknowledge_sensitive=True)
    assert api.client.delete(url, headers=ana).status_code == 403, "Ana no subió este archivo"
    deleted = api.client.delete(url, headers=admin)
    assert deleted.status_code == 200 and deleted.json()["revoked_shares"] == 1
    detail = api.client.get(f"/api/v1/shares/{share['id']}", headers=ana).json()
    assert detail["status"] == "REVOKED"
    assert api.client.get(url, headers=admin).status_code == 404
    event = api.audit(event_type="DOCUMENT_DELETED")[0]
    assert event["metadata"]["revoked_shares"] == 1  # type: ignore[index]
    assert event["metadata"]["filename"] == "doc-delete.pdf"  # type: ignore[index]


def test_uploader_can_delete_own_file(api: Api) -> None:
    from tests.helpers import make_pdf

    ana = api.headers("ana@thinknex.example")
    r = api.client.post(
        "/api/v1/library/documents",
        data={"library_id": "comercial", "classification": "INTERNAL"},
        files={"file": ("propio-borrar.pdf", make_pdf("x"), "application/pdf")},
        headers=ana,
    )
    doc_id = r.json()["document"]["id"]
    deleted = api.client.delete(f"/api/v1/library/documents/{doc_id}", headers=ana)
    assert deleted.status_code == 200 and deleted.json()["revoked_shares"] == 0


def test_admin_can_share(api: Api) -> None:
    r = api.client.post(
        "/api/v1/shares",
        json={
            "document_id": "doc-public",
            "recipient": EXTERNAL,
            "channel": "EMAIL",
            "reason": "Envío desde administración",
        },
        headers=api.admin_headers(),
    )
    assert r.status_code == 201, r.text
    assert r.json()["shared_by"] == "admin@thinknex.example"


def test_admin_can_relax_anyone_link_rule(api: Api) -> None:
    rule = _rule(api, "Enlace para cualquiera con datos personales")
    assert rule["audiences"] == ["ANYONE"] and rule["action"] == "BLOCK"
    body = {
        "document_id": "doc-email",
        "channel": "LINK",
        "audience": "ANYONE",
        "permission": "VIEW",
        "recipient": None,
        "reason": "Folleto con contacto",
        "acknowledge_sensitive": True,
    }
    ana = api.headers("ana@thinknex.example")
    blocked = api.client.post("/api/v1/shares", json=body, headers=ana)
    assert blocked.status_code == 403
    assert blocked.json()["report"]["reasons"] == [rule["message"]]

    admin = api.admin_headers()
    url = f"{POLICIES}/{rule['id']}"
    api.client.put(url, json=_body(rule, enabled=False), headers=admin)
    try:
        warned = api.client.post(
            "/api/v1/shares", json={**body, "acknowledge_sensitive": False}, headers=ana
        )
        assert warned.status_code == 409, "sin la regla, solo pide confirmación"
        created = api.client.post("/api/v1/shares", json=body, headers=ana)
        assert created.status_code == 201, created.text
    finally:
        api.client.put(url, json=_body(rule), headers=admin)
