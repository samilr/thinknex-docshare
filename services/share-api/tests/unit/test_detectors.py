import pytest

from app.sensitivity.detectors import (
    detect,
    extract_text,
    is_valid_rut,
    luhn_valid,
    redact,
    summarize,
)
from tests.helpers import make_pdf


@pytest.mark.parametrize(
    ("rut", "valid"),
    [("17.234.567-0", True), ("18.456.789-K", True), ("12345678-5", True), ("17.234.567-1", False)],
)
def test_rut_check_digit(rut: str, valid: bool) -> None:
    assert is_valid_rut(rut) is valid


def test_luhn() -> None:
    assert luhn_valid("4111 1111 1111 1111")
    assert not luhn_valid("4111 1111 1111 1112")


def test_detects_chilean_personal_data() -> None:
    text = (
        "Trabajador Juan, RUT 17.234.567-0, correo juan@correo.example, fono +56 9 8765 4321. "
        "Tarjeta 4111 1111 1111 1111. Depósito en cuenta corriente N° 00-123-45678-09."
    )
    types = [d.type for d in detect(text)]
    assert sorted(types) == ["BANK_ACCOUNT", "CARD", "EMAIL", "PHONE", "RUT"]


def test_invalid_rut_and_plain_numbers_are_ignored() -> None:
    text = "Folio 17.234.567-1. Disponibilidad 99,92%. Precio 450 UF. Año 2026."
    assert detect(text) == []


def test_card_digits_not_double_counted_as_phone() -> None:
    assert [d.type for d in detect("Tarjeta 4111 1111 1111 1111")] == ["CARD"]


def test_summary_masks_values() -> None:
    summary = summarize(detect("RUT 17.234.567-0 y 18.456.789-K, mail ana@x.example"))
    rut = next(f for f in summary if f.type == "RUT")
    assert rut.count == 2
    assert all("234.567" not in s and "456.789" not in s for s in rut.samples)
    email = next(f for f in summary if f.type == "EMAIL")
    assert email.samples == ["a***@x.example"]


def test_redact_replaces_values() -> None:
    text = "RUT 17.234.567-0, mail ana@x.example."
    assert redact(text, detect(text)) == "RUT [RUT], mail [EMAIL]."


def test_extract_text_from_pdf() -> None:
    text = extract_text(make_pdf("Hola mundo", "RUT 17.234.567-0"), "application/pdf")
    assert text is not None and "17.234.567-0" in text
    assert extract_text(b"\x00\x01", "application/octet-stream") is None
    assert extract_text(b"not a pdf", "application/pdf") is None
