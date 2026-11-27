import hashlib
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.adapters.document_source import SourceDocument, SourcePage
from app.core.errors import NotFoundError
from app.domain.enums import Classification
from app.sensitivity.llm_classifier import LlmAssessment


def make_pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    y = 800
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.save()
    return buffer.getvalue()


class FakeDocumentSource:
    def __init__(self) -> None:
        self.docs: dict[str, tuple[SourceDocument, bytes]] = {}

    def add(self, doc_id: str, classification: Classification, *lines: str) -> None:
        content = make_pdf(*lines)
        meta = SourceDocument(
            id=doc_id,
            title=f"Documento {doc_id}",
            mime_type="application/pdf",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            version=1,
            classification=classification,
            owner="owner@thinknex.example",
        )
        self.docs[doc_id] = (meta, content)

    def list(self, *, q: str | None, limit: int, offset: int) -> SourcePage:
        items = [m for m, _ in self.docs.values()]
        return SourcePage(
            items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
        )

    def get_metadata(self, doc_id: str) -> SourceDocument:
        if doc_id not in self.docs:
            raise NotFoundError("Documento no encontrado en el sistema documental")
        return self.docs[doc_id][0]

    def get_content(self, doc_id: str) -> bytes:
        return self.docs[doc_id][1]

    def ping(self) -> bool:
        return True


class FakeClassifier:
    model = "fake-llm"

    def __init__(self, assessment: LlmAssessment | None) -> None:
        self.assessment = assessment
        self.received: list[str] = []

    def classify(self, *, title: str, redacted_text: str) -> LlmAssessment | None:
        self.received.append(redacted_text)
        return self.assessment
