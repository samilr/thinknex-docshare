"""Política de compartición configurable: reglas que el ADMIN crea, edita, desactiva o elimina.

Cada regla dice "si se cumplen estas condiciones, ADVERTIR o BLOQUEAR". Una condición vacía
significa "cualquiera". Se evalúan todas las reglas activas y gana la más restrictiva
(BLOCK > WARN > ALLOW). Si ninguna aplica, se permite.

Condiciones:
- clasificaciones del documento;
- destinatario interno, externo o cualquiera ("cualquiera con el enlace" cuenta como externo);
- tipos de datos personales detectados (la regla aplica si hay AL MENOS uno de ellos);
- canales de envío.

Reglas por defecto (equivalentes a la matriz original):

| Clasificación | Interno | Externo                              |
|---------------|---------|--------------------------------------|
| PUBLIC        | ALLOW   | ALLOW (WARN si hay datos personales) |
| INTERNAL      | ALLOW   | ALLOW (WARN si hay datos personales) |
| CONFIDENTIAL  | ALLOW   | WARN                                 |
| RESTRICTED    | WARN    | BLOCK                                |

Fuera de las reglas (fijo, no configurable): el LLM (si está activo) solo puede elevar ALLOW a
WARN para externos, y un documento cuyo contenido no se pudo analizar requiere confirmación.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.enums import Classification, Decision
from app.sensitivity.detectors import FindingSummary
from app.sensitivity.llm_classifier import LlmAssessment, LlmSensitivity

FINDING_TYPES = ("RUT", "EMAIL", "PHONE", "CARD", "BANK_ACCOUNT")
_SEVERITY = {Decision.ALLOW: 0, Decision.WARN: 1, Decision.BLOCK: 2}


class RecipientScope(StrEnum):
    ANY = "ANY"
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"


@dataclass(frozen=True)
class PolicyRule:
    name: str
    action: Decision  # WARN o BLOCK
    message: str
    classifications: frozenset[str] = field(default_factory=frozenset)
    recipient: RecipientScope = RecipientScope.ANY
    finding_types: frozenset[str] = field(default_factory=frozenset)
    channels: frozenset[str] = field(default_factory=frozenset)

    def matches(
        self,
        classification: Classification,
        found: set[str],
        is_external: bool,
        channel: str | None,
    ) -> bool:
        if self.classifications and classification.value not in self.classifications:
            return False
        if self.recipient is RecipientScope.EXTERNAL and not is_external:
            return False
        if self.recipient is RecipientScope.INTERNAL and is_external:
            return False
        if self.finding_types and not (self.finding_types & found):
            return False
        # Sin canal (revisión previa) no se descarta: se evalúa como el peor caso.
        return not (self.channels and channel is not None and channel not in self.channels)


DEFAULT_RULES: tuple[PolicyRule, ...] = (
    PolicyRule(
        name="Restringidos fuera de la organización",
        action=Decision.BLOCK,
        message="Documento RESTRICTED: no puede compartirse con destinatarios externos.",
        classifications=frozenset({"RESTRICTED"}),
        recipient=RecipientScope.EXTERNAL,
    ),
    PolicyRule(
        name="Restringidos entre áreas",
        action=Decision.WARN,
        message="Documento RESTRICTED: requiere confirmación incluso entre áreas internas.",
        classifications=frozenset({"RESTRICTED"}),
        recipient=RecipientScope.INTERNAL,
    ),
    PolicyRule(
        name="Confidenciales a externos",
        action=Decision.WARN,
        message="Documento CONFIDENTIAL dirigido a un destinatario externo.",
        classifications=frozenset({"CONFIDENTIAL"}),
        recipient=RecipientScope.EXTERNAL,
    ),
    PolicyRule(
        name="Datos personales a externos",
        action=Decision.WARN,
        message="Contiene datos personales o financieros y sale de la organización.",
        recipient=RecipientScope.EXTERNAL,
        finding_types=frozenset(FINDING_TYPES),
    ),
)


@dataclass(frozen=True)
class PolicyOutcome:
    decision: Decision
    reasons: list[str]
    matched: list[str]


def evaluate(
    *,
    classification: Classification,
    findings: Sequence[FindingSummary],
    is_external: bool,
    llm: LlmAssessment | None,
    rules: Iterable[PolicyRule] = DEFAULT_RULES,
    channel: str | None = None,
) -> PolicyOutcome:
    rules = list(rules)
    found = {f.type for f in findings}
    decision = Decision.ALLOW
    reasons: list[str] = []
    matched: list[str] = []
    for rule in rules:
        if not rule.matches(classification, found, is_external, channel):
            continue
        matched.append(rule.name)
        hit = sorted(rule.finding_types & found)
        reasons.append(f"{rule.message} ({', '.join(hit)})" if hit else rule.message)
        if _SEVERITY[rule.action] > _SEVERITY[decision]:
            decision = rule.action

    if llm and llm.sensitivity is LlmSensitivity.HIGH and is_external:
        reasons.append(f"Análisis asistido por IA: sensibilidad ALTA. {llm.rationale}")
        if decision is Decision.ALLOW:
            decision = Decision.WARN

    # Ante un BLOCK, solo se muestran los motivos del bloqueo.
    if decision is Decision.BLOCK:
        reasons = [r.message for r in rules if r.action is Decision.BLOCK and r.name in matched]
    return PolicyOutcome(decision, reasons, matched)


def decide(
    *,
    classification: Classification,
    findings: Sequence[FindingSummary],
    is_external: bool,
    llm: LlmAssessment | None,
    rules: Iterable[PolicyRule] = DEFAULT_RULES,
    channel: str | None = None,
) -> tuple[Decision, list[str]]:
    outcome = evaluate(
        classification=classification,
        findings=findings,
        is_external=is_external,
        llm=llm,
        rules=rules,
        channel=channel,
    )
    return outcome.decision, outcome.reasons
