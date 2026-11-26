import io
from datetime import UTC, datetime, timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from app.adapters.storage import snapshot_key
from app.db.models import Share
from app.services import retention_service
from tests.integration.conftest import Api

pytestmark = pytest.mark.integration


def test_end_to_end_email_share(api: Api) -> None:
    share = api.share()
    assert share["status"] == "ACTIVE"
    assert share["notification_status"] == "SENT"
    assert "/s/" not in str(share), "el enlace nunca se devuelve a quien comparte"

    token = api.last_link_token()
    landing = api.client.get(f"/s/{token}")
    assert landing.status_code == 200
    assert "Ana Rojas" in landing.text
    assert "Documento doc-public" not in landing.text, "no se revela el título antes del OTP"
    assert "nonce-" in landing.headers["content-security-policy"]
    assert landing.headers["cache-control"] == "no-store"

    access = api.unlock(token)
    download = api.client.get(f"/s/{token}/download", headers={"Authorization": f"Bearer {access}"})
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    pdf_text = PdfReader(io.BytesIO(download.content)).pages[0].extract_text()
    assert "Catalogo de productos 2026" in pdf_text
    assert "Compartido con Pedro Externo" in pdf_text

    events = api.audit(share_id=str(share["id"]))
    assert [e["event_type"] for e in reversed(events)] == [
        "SHARE_CREATED",
        "NOTIFICATION_SENT",
        "LINK_OPENED",
        "OTP_SENT",
        "OTP_VERIFIED",
        "DOCUMENT_ACCESSED",
    ]
    created = events[-1]
    assert created["channel"] == "EMAIL"
    assert created["actor_type"] == "USER"
    assert created["actor"] == "Ana Rojas <ana@demo-corp.example>"
    assert events[0]["actor"] == "Pedro Externo <p***@cliente.example>"
    assert created["metadata"]["reason"] == "Envío de catálogo solicitado"  # type: ignore[index]
    accessed = events[0]
    assert accessed["actor_type"] == "RECIPIENT"
    assert accessed["metadata"]["watermarked"] is True  # type: ignore[index]

    verify = api.client.get("/api/v1/audit/verify", headers=api.headers("carla@demo-corp.example"))
    assert verify.json()["valid"] is True


def test_sensitive_document_requires_acknowledgement(api: Api) -> None:
    body = {
        "document_id": "doc-pii",
        "recipient": {"name": "Ext", "phone": "+56 9 1111 2222"},
        "channel": "WHATSAPP",
        "reason": "Certificado solicitado por el cliente",
    }
    r = api.client.post("/api/v1/shares", json=body, headers=api.headers("ana@demo-corp.example"))
    assert r.status_code == 409
    assert r.headers["content-type"] == "application/problem+json"
    finding_types = {f["type"] for f in r.json()["report"]["findings"]}
    assert {"RUT", "PHONE"} <= finding_types
    assert "18.456.789-K" not in r.text, "los valores detectados nunca se exponen en claro"

    share = api.share(**{**body, "acknowledge_sensitive": True})
    assert share["sensitivity_decision"] == "WARN"
    assert share["channel"] == "WHATSAPP"
    assert api.last_message("LINK")["channel"] == "WHATSAPP"


def test_restricted_to_external_is_blocked_and_audited(api: Api) -> None:
    body = {
        "document_id": "doc-restricted",
        "recipient": {"name": "Ext", "email": "x@otra.example"},
        "channel": "EMAIL",
        "reason": "intento",
        "acknowledge_sensitive": True,
    }
    r = api.client.post("/api/v1/shares", json=body, headers=api.headers("bruno@demo-corp.example"))
    assert r.status_code == 403
    blocked = api.audit(event_type="SHARE_BLOCKED")
    assert blocked and blocked[0]["channel"] == "EMAIL"
    by_document = {e["event_type"] for e in api.audit(document_id="doc-restricted")}
    assert {"SENSITIVITY_CHECKED", "SHARE_BLOCKED"} <= by_document


def test_restricted_to_internal_warns(api: Api) -> None:
    body = {
        "document_id": "doc-restricted",
        "recipient": {"name": "Carla", "email": "carla@demo-corp.example"},
        "channel": "EMAIL",
        "reason": "Revisión interna",
    }
    r = api.client.post("/api/v1/shares", json=body, headers=api.headers("ana@demo-corp.example"))
    assert r.status_code == 409


def test_wrong_otp_locks_share(api: Api) -> None:
    share = api.share()
    token = api.last_link_token()
    api.client.post(f"/s/{token}/otp")
    good = api.last_otp()
    wrong = "000000" if good != "000000" else "111111"
    for attempt in range(1, 5):
        r = api.client.post(f"/s/{token}/verify", json={"code": wrong})
        assert r.status_code == 401
        assert r.json()["remaining_attempts"] == 5 - attempt
    r = api.client.post(f"/s/{token}/verify", json={"code": wrong})
    assert r.status_code == 404
    assert api.client.post(f"/s/{token}/verify", json={"code": good}).status_code == 404
    detail = api.client.get(
        f"/api/v1/shares/{share['id']}", headers=api.headers("ana@demo-corp.example")
    )
    assert detail.json()["status"] == "LOCKED"


def test_max_accesses_is_enforced(api: Api) -> None:
    api.share(max_accesses=1)
    token = api.last_link_token()
    access = api.unlock(token)
    auth = {"Authorization": f"Bearer {access}"}
    assert api.client.get(f"/s/{token}/download", headers=auth).status_code == 200
    assert api.client.get(f"/s/{token}/download", headers=auth).status_code == 404
    denied = api.audit(event_type="ACCESS_DENIED")
    assert denied[0]["metadata"]["reason"] == "EXHAUSTED"  # type: ignore[index]


def test_download_requires_verified_otp(api: Api) -> None:
    api.share()
    token = api.last_link_token()
    assert api.client.get(f"/s/{token}/download").status_code == 404
    other_token = api.client.post(
        "/api/v1/auth/token",
        data={"username": "ana@demo-corp.example", "password": "integration-password-1"},
    ).json()["access_token"]
    r = api.client.get(f"/s/{token}/download", headers={"Authorization": f"Bearer {other_token}"})
    assert r.status_code == 404, "un JWT de usuario interno no sirve como token de descarga"


def test_revocation(api: Api) -> None:
    share = api.share()
    token = api.last_link_token()
    url = f"/api/v1/shares/{share['id']}/revoke"
    assert api.client.post(url, headers=api.headers("bruno@demo-corp.example")).status_code == 404
    r = api.client.post(url, headers=api.headers("ana@demo-corp.example"))
    assert r.status_code == 200 and r.json()["status"] == "REVOKED"
    assert api.client.post(url, headers=api.headers("ana@demo-corp.example")).status_code == 409
    landing = api.client.get(f"/s/{token}")
    assert landing.status_code == 404 and "Enlace no disponible" in landing.text
    assert api.client.post(f"/s/{token}/otp").status_code == 404


def test_expired_share(api: Api) -> None:
    share = api.share()
    token = api.last_link_token()
    with api.components.session_factory() as db, db.begin():
        db.execute(
            update(Share)
            .where(Share.id == share["id"])
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )
    assert api.client.post(f"/s/{token}/otp").status_code == 404
    events = [e["event_type"] for e in api.audit(share_id=str(share["id"]))]
    assert events[:2] == ["ACCESS_DENIED", "SHARE_EXPIRED"]


def test_unknown_link_is_audited(api: Api) -> None:
    assert api.client.post("/s/not-a-real-token/otp").status_code == 404
    denied = api.audit(event_type="ACCESS_DENIED")
    assert denied[0]["metadata"]["reason"] == "UNKNOWN_TOKEN"  # type: ignore[index]


def test_role_enforcement(api: Api) -> None:
    assert api.client.get("/api/v1/shares").status_code == 401
    r = api.client.post(
        "/api/v1/shares",
        json={
            "document_id": "doc-public",
            "recipient": {"name": "x", "email": "x@y.example"},
            "channel": "EMAIL",
            "reason": "test",
        },
        headers=api.headers("carla@demo-corp.example"),
    )
    assert r.status_code == 403
    assert (
        api.client.get("/api/v1/audit", headers=api.headers("ana@demo-corp.example")).status_code
        == 403
    )


def test_channel_contact_validation(api: Api) -> None:
    r = api.client.post(
        "/api/v1/shares",
        json={
            "document_id": "doc-public",
            "recipient": {"name": "x", "email": "x@y.example"},
            "channel": "SMS",
            "reason": "test",
        },
        headers=api.headers("ana@demo-corp.example"),
    )
    assert r.status_code == 422


def test_retention_purges_snapshot_but_keeps_hash(api: Api) -> None:
    share = api.share(document_id="doc-retention")
    meta, _ = api.components.source.docs["doc-retention"]  # type: ignore[attr-defined]
    key = snapshot_key(meta.sha256)
    assert api.components.storage.exists(key)
    with api.components.session_factory() as db, db.begin():
        db.execute(
            update(Share)
            .where(Share.id == share["id"])
            .values(expires_at=datetime.now(UTC) - timedelta(days=3))
        )
    with api.components.session_factory() as db, db.begin():
        result = retention_service.run(db, api.components.storage, grace_hours=24)
    assert result.purged_snapshots >= 1
    assert not api.components.storage.exists(key)
    purged = api.audit(event_type="SNAPSHOT_PURGED")
    assert any(e["metadata"]["sha256"] == meta.sha256 for e in purged)  # type: ignore[index]


def test_audit_table_is_append_only(api: Api) -> None:
    api.share()
    with api.components.session_factory() as db:
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("UPDATE audit_events SET event_type = 'X'"))
        db.rollback()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text("DELETE FROM audit_events"))
        db.rollback()


def test_tampering_is_detected_by_hash_chain(api: Api) -> None:
    api.share()
    headers = api.headers("carla@demo-corp.example")
    assert api.client.get("/api/v1/audit/verify", headers=headers).json()["valid"] is True

    with api.components.session_factory() as db, db.begin():
        db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update_delete"))
        target, original = db.execute(
            text("SELECT id, channel FROM audit_events WHERE channel = 'EMAIL' ORDER BY id LIMIT 1")
        ).one()
        db.execute(text("UPDATE audit_events SET channel = 'SMS' WHERE id = :id"), {"id": target})
        db.execute(text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update_delete"))
    try:
        result = api.client.get("/api/v1/audit/verify", headers=headers).json()
        assert result["valid"] is False
        assert result["first_broken_event_id"] == target
    finally:
        with api.components.session_factory() as db, db.begin():
            db.execute(
                text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_no_update_delete")
            )
            db.execute(
                text("UPDATE audit_events SET channel = :c WHERE id = :id"),
                {"c": original, "id": target},
            )
            db.execute(
                text("ALTER TABLE audit_events ENABLE TRIGGER audit_events_no_update_delete")
            )
    assert api.client.get("/api/v1/audit/verify", headers=headers).json()["valid"] is True
