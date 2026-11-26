import io
import uuid
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from app.adapters.watermark import apply_watermark
from app.core import security
from app.core.logging import redact_path
from app.db.models import AuditEvent
from app.services.audit_service import GENESIS_HASH, compute_hash
from tests.helpers import make_pdf

SECRET = "unit-test-secret-with-at-least-32-bytes"


def test_user_token_roundtrip_and_type_confusion() -> None:
    uid = uuid.uuid4()
    token = security.create_user_token(uid, ["SHARER"], SECRET, 5)
    assert security.decode_user_token(token, SECRET)["sub"] == str(uid)
    with pytest.raises(security.InvalidTokenError):
        security.decode_user_token(token, "x" * 32)
    download = security.create_download_token(uid, SECRET, 5)
    with pytest.raises(security.InvalidTokenError):  # un token de descarga no sirve como sesión
        security.decode_user_token(download, SECRET)


def test_otp_is_bound_to_share() -> None:
    share_a, share_b = uuid.uuid4(), uuid.uuid4()
    mac = security.otp_mac("123456", share_a, "k")
    assert security.verify_otp("123456", share_a, "k", mac)
    assert not security.verify_otp("123456", share_b, "k", mac)
    assert not security.verify_otp("654321", share_a, "k", mac)


def test_share_token_entropy_and_hash() -> None:
    token = security.generate_share_token()
    assert len(token) >= 43
    assert security.hash_token(token) != token
    assert len(security.hash_token(token)) == 64


def test_masking() -> None:
    assert security.mask_email("juan.perez@correo.example") == "j***@correo.example"
    assert security.mask_phone("+56 9 8765 4321") == "***4321"


def test_link_tokens_are_redacted_from_logs() -> None:
    assert redact_path("/s/abcDEF123/download") == "/s/***/download"
    assert redact_path("/api/v1/shares") == "/api/v1/shares"


def test_watermark_is_applied_and_content_preserved() -> None:
    original = make_pdf("Contenido original")
    stamped, applied = apply_watermark(original, "application/pdf", "Compartido con Ana")
    assert applied
    text = PdfReader(io.BytesIO(stamped)).pages[0].extract_text()
    assert "Contenido original" in text and "Compartido con Ana" in text
    same, applied = apply_watermark(b"zip", "application/zip", "x")
    assert (same, applied) == (b"zip", False)


def test_audit_hash_changes_with_any_field() -> None:
    event = AuditEvent(
        occurred_at=datetime(2026, 11, 26, 12, 0, tzinfo=UTC),
        event_type="SHARE_CREATED",
        actor_type="USER",
        actor_id="u1",
        share_id=None,
        document_id=None,
        channel="EMAIL",
        ip="10.0.0.1",
        user_agent="ua",
        details={"b": 1, "a": 2},
    )
    original = compute_hash(GENESIS_HASH, event)
    event.details = {"a": 2, "b": 1}
    assert compute_hash(GENESIS_HASH, event) == original  # JSON canónico: el orden no importa
    event.channel = "WHATSAPP"
    assert compute_hash(GENESIS_HASH, event) != original
    assert compute_hash("f" * 64, event) != compute_hash(GENESIS_HASH, event)
