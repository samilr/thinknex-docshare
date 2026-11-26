"""Detectores deterministas de datos personales y financieros (contexto chileno).

Siempre activos, explicables, sin costo y sin enviar datos a terceros. Los valores detectados
nunca se persisten en claro: solo tipo, cantidad y muestras enmascaradas.
"""

import io
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.security import mask_email

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Detection:
    type: str
    value: str
    start: int
    end: int


class FindingSummary(BaseModel):
    type: str
    count: int
    samples: list[str]


def rut_check_digit(body: int) -> str:
    total, factor = 0, 2
    for digit in reversed(str(body)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - total % 11
    return {11: "0", 10: "K"}.get(remainder, str(remainder))


def is_valid_rut(value: str) -> bool:
    body, _, dv = value.replace(".", "").upper().partition("-")
    return body.isdigit() and rut_check_digit(int(body)) == dv


def luhn_valid(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    checksum = 0
    for i, digit in enumerate(reversed(digits)):
        if i % 2 == 1:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        checksum += digit
    return checksum % 10 == 0


@dataclass(frozen=True)
class _Rule:
    type: str
    pattern: re.Pattern[str]
    validator: Callable[[str], bool] | None = None
    group: int = 0


# El orden importa: tarjetas antes que teléfonos para no confundir dígitos solapados.
_RULES = [
    _Rule(
        "RUT", re.compile(r"(?<![\d.])(\d{1,2}(?:\.\d{3}){2}|\d{7,8})-[\dkK](?![\w])"), is_valid_rut
    ),
    _Rule("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    _Rule("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"), luhn_valid),
    _Rule(
        "BANK_ACCOUNT",
        re.compile(
            r"(?i)(?:cuenta\s+(?:corriente|vista|rut|de\s+ahorros?)|cta\.?\s*cte\.?)"
            r"\D{0,15}?(\d[\d-]{5,}\d)"
        ),
        group=1,
    ),
    _Rule("PHONE", re.compile(r"(?<!\d)(?:\+?56[\s-]?)?9[\s-]?\d{4}[\s-]?\d{4}(?!\d)")),
]


def detect(text: str) -> list[Detection]:
    detections: list[Detection] = []
    taken: list[tuple[int, int]] = []
    for rule in _RULES:
        for match in rule.pattern.finditer(text):
            start, end = match.span(rule.group)
            value = match.group(rule.group)
            if rule.validator and not rule.validator(match.group(0)):
                continue
            if any(start < t_end and end > t_start for t_start, t_end in taken):
                continue
            taken.append((start, end))
            detections.append(Detection(rule.type, value, start, end))
    return sorted(detections, key=lambda d: d.start)


def mask_value(detection: Detection) -> str:
    if detection.type == "EMAIL":
        return mask_email(detection.value)
    tail = detection.value[-4:]
    return f"{'*' * max(len(detection.value) - 4, 3)}{tail}"


def summarize(detections: list[Detection], max_samples: int = 2) -> list[FindingSummary]:
    grouped: dict[str, list[Detection]] = {}
    for detection in detections:
        grouped.setdefault(detection.type, []).append(detection)
    return [
        FindingSummary(
            type=kind, count=len(items), samples=[mask_value(d) for d in items[:max_samples]]
        )
        for kind, items in sorted(grouped.items())
    ]


def redact(text: str, detections: list[Detection]) -> str:
    """Reemplaza cada dato detectado por [TIPO]. Se usa antes de enviar texto a un LLM."""
    out, cursor = [], 0
    for detection in sorted(detections, key=lambda d: d.start):
        out.append(text[cursor : detection.start])
        out.append(f"[{detection.type}]")
        cursor = detection.end
    out.append(text[cursor:])
    return "".join(out)


def extract_text(content: bytes, mime_type: str) -> str | None:
    """Texto plano del documento, o None si el formato no es soportado o falla la extracción."""
    if mime_type.startswith("text/"):
        return content.decode("utf-8", errors="replace")
    if mime_type != "application/pdf":
        return None
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except (PyPdfError, ValueError) as exc:
        logger.warning("no se pudo extraer texto", extra={"extra_fields": {"error": str(exc)}})
        return None
