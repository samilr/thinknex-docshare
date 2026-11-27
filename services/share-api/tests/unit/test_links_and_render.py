import io

import pytest
from PIL import Image
from pydantic import ValidationError

from app.adapters import render
from app.domain.enums import Audience, Classification, Decision, Permission
from app.schemas import ShareRequest
from app.sensitivity.checker import SensitivityReport
from app.services.share_service import apply_link_policy
from tests.helpers import make_pdf


def _report(decision: Decision, classification: Classification) -> SensitivityReport:
    return SensitivityReport(
        decision=decision,
        reasons=[],
        classification=classification,
        recipient_external=True,
        findings=[],
        text_extracted=True,
        engine="test",
    )


@pytest.mark.parametrize(
    ("decision", "classification", "audience", "permission", "expected"),
    [
        (Decision.ALLOW, Classification.PUBLIC, Audience.ANYONE, Permission.VIEW, Decision.ALLOW),
        (Decision.WARN, Classification.INTERNAL, Audience.ANYONE, Permission.VIEW, Decision.BLOCK),
        (Decision.WARN, Classification.INTERNAL, Audience.SPECIFIC, Permission.VIEW, Decision.WARN),
        (
            Decision.WARN,
            Classification.RESTRICTED,
            Audience.SPECIFIC,
            Permission.EDIT,
            Decision.BLOCK,
        ),
        (
            Decision.WARN,
            Classification.RESTRICTED,
            Audience.SPECIFIC,
            Permission.DOWNLOAD,
            Decision.WARN,
        ),
    ],
)
def test_link_policy(
    decision: Decision,
    classification: Classification,
    audience: Audience,
    permission: Permission,
    expected: Decision,
) -> None:
    result = apply_link_policy(_report(decision, classification), audience, permission)
    assert result.decision is expected
    if expected is Decision.BLOCK:
        assert result.reasons


def test_share_request_rules() -> None:
    ok = ShareRequest(
        document_id="d", channel="LINK", audience="ANYONE", permission="VIEW", reason="motivo"
    )
    assert ok.recipient is None
    legacy = ShareRequest(
        document_id="d",
        channel="EMAIL",
        recipient={"name": "x", "email": "x@y.example"},
        reason="motivo",
    )
    assert legacy.permission is Permission.DOWNLOAD and legacy.audience is Audience.SPECIFIC
    for bad in (
        {"channel": "LINK", "audience": "ANYONE", "permission": "EDIT"},
        {"channel": "SMS", "audience": "ANYONE"},
        {"channel": "LINK", "audience": "SPECIFIC"},
    ):
        with pytest.raises(ValidationError):
            ShareRequest(document_id="d", reason="motivo", **bad)  # type: ignore[arg-type]


def test_render_pdf_page_with_watermark() -> None:
    pdf = make_pdf("Linea uno", "Linea dos")
    assert render.kind("application/pdf") == "pdf"
    assert render.page_count(pdf, "application/pdf") == 1
    png = render.render_page(pdf, "application/pdf", 0, "Vista protegida · Pedro")
    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.width > 500
    # La marca de agua (rojiza) cambia píxeles que en el original serían blancos.
    pixels = image.convert("RGB").get_flattened_data()
    assert any(r > g + 20 for r, g, _ in pixels)
    with pytest.raises(IndexError):
        render.render_page(pdf, "application/pdf", 1, "x")


def test_render_image_and_unsupported() -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buffer, format="PNG")
    png = render.render_page(buffer.getvalue(), "image/png", 0, "stamp")
    assert png.startswith(b"\x89PNG")
    assert render.page_count(b"hola", "text/plain") == 1
    with pytest.raises(render.UnsupportedPreview):
        render.render_page(b"hola", "text/plain", 0, "x")
