from typing import Any

from pydantic import BaseModel

from app.domain.enums import Classification, Decision
from app.sensitivity.detectors import FindingSummary, detect, extract_text, redact, summarize
from app.sensitivity.llm_classifier import LlmAssessment, SensitivityClassifier
from app.sensitivity.policy import decide


class SensitivityReport(BaseModel):
    decision: Decision
    reasons: list[str]
    classification: Classification
    recipient_external: bool
    findings: list[FindingSummary]
    text_extracted: bool
    engine: str
    llm: LlmAssessment | None = None
    llm_model: str | None = None
    llm_input_truncated: bool = False

    def audit_summary(self) -> dict[str, Any]:
        """Versión mínima para la auditoría: sin muestras ni texto libre."""
        return {
            "decision": self.decision.value,
            "engine": self.engine,
            "classification": self.classification.value,
            "recipient_external": self.recipient_external,
            "findings": {f.type: f.count for f in self.findings},
            "llm_sensitivity": self.llm.sensitivity.value if self.llm else None,
        }


class SensitivityChecker:
    def __init__(self, classifier: SensitivityClassifier | None, llm_max_chars: int) -> None:
        self._classifier = classifier
        self._llm_max_chars = llm_max_chars

    def check(
        self,
        *,
        content: bytes,
        mime_type: str,
        title: str,
        classification: Classification,
        is_external: bool,
    ) -> SensitivityReport:
        text = extract_text(content, mime_type)
        detections = detect(text) if text else []
        findings = summarize(detections)

        llm: LlmAssessment | None = None
        engine = "rules"
        truncated = False
        if self._classifier is not None and text:
            redacted = redact(text, detections)
            truncated = len(redacted) > self._llm_max_chars
            llm = self._classifier.classify(
                title=title, redacted_text=redacted[: self._llm_max_chars]
            )
            engine = "rules+llm" if llm else "rules (llm no disponible)"

        decision, reasons = decide(
            classification=classification, findings=findings, is_external=is_external, llm=llm
        )
        if text is None and is_external:
            reasons.append("No fue posible analizar el contenido del documento.")
            if decision is Decision.ALLOW:
                decision = Decision.WARN

        return SensitivityReport(
            decision=decision,
            reasons=reasons,
            classification=classification,
            recipient_external=is_external,
            findings=findings,
            text_extracted=text is not None,
            engine=engine,
            llm=llm,
            llm_model=self._classifier.model if llm and self._classifier else None,
            llm_input_truncated=truncated,
        )
