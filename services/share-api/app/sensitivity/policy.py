"""Política de compartición: clasificación x hallazgos x tipo de destinatario -> decisión.

| Clasificación | Interno | Externo                         |
|---------------|---------|---------------------------------|
| PUBLIC        | ALLOW   | ALLOW (WARN si hay datos personales) |
| INTERNAL      | ALLOW   | ALLOW (WARN si hay datos personales) |
| CONFIDENTIAL  | ALLOW   | WARN                            |
| RESTRICTED    | WARN    | BLOCK                           |

El LLM (si está activo) solo puede elevar ALLOW -> WARN para destinatarios externos.
"""

from app.domain.enums import Classification, Decision
from app.sensitivity.detectors import FindingSummary
from app.sensitivity.llm_classifier import LlmAssessment, LlmSensitivity


def decide(
    *,
    classification: Classification,
    findings: list[FindingSummary],
    is_external: bool,
    llm: LlmAssessment | None,
) -> tuple[Decision, list[str]]:
    if classification is Classification.RESTRICTED and is_external:
        return Decision.BLOCK, [
            "Documento RESTRICTED: no puede compartirse con destinatarios externos."
        ]

    reasons: list[str] = []
    if classification is Classification.RESTRICTED:
        reasons.append("Documento RESTRICTED: requiere confirmación incluso entre áreas internas.")
    if classification is Classification.CONFIDENTIAL and is_external:
        reasons.append("Documento CONFIDENTIAL dirigido a un destinatario externo.")
    if findings and is_external:
        kinds = ", ".join(f.type for f in findings)
        reasons.append(
            f"Contiene datos personales o financieros ({kinds}) y sale de la organización."
        )
    if llm and llm.sensitivity is LlmSensitivity.HIGH and is_external:
        reasons.append(f"Análisis asistido por IA: sensibilidad ALTA. {llm.rationale}")

    return (Decision.WARN if reasons else Decision.ALLOW), reasons
