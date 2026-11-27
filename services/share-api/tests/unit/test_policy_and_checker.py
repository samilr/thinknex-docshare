import pytest

from app.domain.enums import Classification, Decision
from app.sensitivity.checker import SensitivityChecker
from app.sensitivity.detectors import FindingSummary
from app.sensitivity.llm_classifier import LlmAssessment, LlmCategory, LlmSensitivity
from app.sensitivity.policy import decide
from tests.helpers import FakeClassifier, make_pdf

PII = [FindingSummary(type="RUT", count=1, samples=["***7-0"])]
HIGH = LlmAssessment(
    sensitivity=LlmSensitivity.HIGH, categories=[LlmCategory.STRATEGIC], rationale="Estrategia."
)


@pytest.mark.parametrize(
    ("classification", "findings", "external", "expected"),
    [
        (Classification.PUBLIC, [], True, Decision.ALLOW),
        (Classification.INTERNAL, [], True, Decision.ALLOW),
        (Classification.INTERNAL, PII, False, Decision.ALLOW),
        (Classification.INTERNAL, PII, True, Decision.WARN),
        (Classification.CONFIDENTIAL, [], False, Decision.ALLOW),
        (Classification.CONFIDENTIAL, [], True, Decision.WARN),
        (Classification.RESTRICTED, [], False, Decision.WARN),
        (Classification.RESTRICTED, [], True, Decision.BLOCK),
    ],
)
def test_policy_matrix(
    classification: Classification,
    findings: list[FindingSummary],
    external: bool,
    expected: Decision,
) -> None:
    decision, reasons = decide(
        classification=classification, findings=findings, is_external=external, llm=None
    )
    assert decision is expected
    assert bool(reasons) is (expected is not Decision.ALLOW)


def test_llm_can_only_escalate_to_warn() -> None:
    decision, reasons = decide(
        classification=Classification.INTERNAL, findings=[], is_external=True, llm=HIGH
    )
    assert decision is Decision.WARN
    assert "IA" in reasons[0]
    decision, _ = decide(
        classification=Classification.INTERNAL, findings=[], is_external=False, llm=HIGH
    )
    assert decision is Decision.ALLOW


def test_checker_sends_only_redacted_text_to_llm() -> None:
    fake = FakeClassifier(HIGH)
    report = SensitivityChecker(fake, llm_max_chars=10_000).check(
        content=make_pdf("Cliente RUT 17.234.567-0", "Plan de expansion"),
        mime_type="application/pdf",
        title="t",
        classification=Classification.INTERNAL,
        is_external=True,
    )
    assert report.engine == "rules+llm"
    assert report.decision is Decision.WARN
    assert "17.234.567-0" not in fake.received[0]
    assert "[RUT]" in fake.received[0]


def test_checker_degrades_when_llm_unavailable() -> None:
    report = SensitivityChecker(FakeClassifier(None), llm_max_chars=100).check(
        content=make_pdf("Catalogo publico"),
        mime_type="application/pdf",
        title="t",
        classification=Classification.PUBLIC,
        is_external=True,
    )
    assert report.engine == "rules (llm no disponible)"
    assert report.decision is Decision.ALLOW


def test_unreadable_document_to_external_is_warned() -> None:
    report = SensitivityChecker(None, llm_max_chars=100).check(
        content=b"binary",
        mime_type="application/zip",
        title="t",
        classification=Classification.PUBLIC,
        is_external=True,
    )
    assert report.decision is Decision.WARN
    assert not report.text_extracted


def test_custom_rules_most_restrictive_wins_and_channel_filter() -> None:
    from app.sensitivity.policy import DEFAULT_RULES, PolicyRule, RecipientScope, evaluate

    email_only = [FindingSummary(type="EMAIL", count=1, samples=["j***@x.example"])]
    no_email = [
        r
        if r.name != "Datos personales a externos"
        else PolicyRule(
            name=r.name,
            action=r.action,
            message=r.message,
            recipient=r.recipient,
            finding_types=r.finding_types - {"EMAIL"},
        )
        for r in DEFAULT_RULES
    ]
    relaxed = evaluate(
        classification=Classification.INTERNAL,
        findings=email_only,
        is_external=True,
        llm=None,
        rules=no_email,
    )
    assert relaxed.decision is Decision.ALLOW and relaxed.matched == []

    whatsapp = PolicyRule(
        name="Sin WhatsApp",
        action=Decision.BLOCK,
        message="No por WhatsApp.",
        recipient=RecipientScope.ANY,
        channels=frozenset({"WHATSAPP"}),
    )
    rules = [*DEFAULT_RULES, whatsapp]
    by_whatsapp = evaluate(
        classification=Classification.INTERNAL,
        findings=email_only,
        is_external=True,
        llm=None,
        rules=rules,
        channel="WHATSAPP",
    )
    assert by_whatsapp.decision is Decision.BLOCK
    assert by_whatsapp.reasons == ["No por WhatsApp."]
    assert set(by_whatsapp.matched) == {"Datos personales a externos", "Sin WhatsApp"}
    by_email = evaluate(
        classification=Classification.INTERNAL,
        findings=email_only,
        is_external=True,
        llm=None,
        rules=rules,
        channel="EMAIL",
    )
    assert by_email.decision is Decision.WARN
    assert "(EMAIL)" in by_email.reasons[0]
