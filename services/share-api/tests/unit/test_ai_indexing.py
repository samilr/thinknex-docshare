import io

from app.ai.chunking import chunk_pages, estimate_tokens
from app.ai.extract import DOCX, XLSX, PageText, extract_pages
from app.ai.providers import FakeEmbedder
from tests.helpers import make_pdf


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_chunking_respects_size_pages_and_overlap() -> None:
    para = " ".join(f"palabra{i}" for i in range(120))  # ~160 tokens
    pages = [PageText(1, f"{para}\n\n{para}"), PageText(2, f"{para}\n\n{para}")]
    chunks = chunk_pages(pages, max_tokens=350, overlap=170)
    assert len(chunks) >= 2
    assert all(estimate_tokens(c.text) <= 350 + 170 for c in chunks)
    assert chunks[0].page_from == 1 and chunks[-1].page_to == 2
    # Con solape, el último párrafo de un fragmento reaparece al inicio del siguiente.
    assert chunks[1].text.startswith(chunks[0].text.split("\n\n")[-1][:40])


def test_long_paragraph_is_split() -> None:
    text = " ".join(f"w{i}" for i in range(3000))
    chunks = chunk_pages([PageText(1, text)], max_tokens=500, overlap=0)
    assert len(chunks) >= 8
    assert all(estimate_tokens(c.text) <= 520 for c in chunks)


def test_extract_pdf_docx_xlsx_txt() -> None:
    pdf = extract_pages(make_pdf("Informe trimestral", "Ventas en alza"), "application/pdf")
    assert pdf and "Ventas en alza" in pdf[0].text and pdf[0].page == 1

    from docx import Document

    doc = Document()
    doc.add_paragraph("Política de vacaciones")
    doc.add_paragraph("Cada persona tiene 15 días hábiles.")
    buffer = io.BytesIO()
    doc.save(buffer)
    docx = extract_pages(buffer.getvalue(), DOCX)
    assert "15 días hábiles" in docx[0].text

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Presupuesto"
    ws.append(["Área", "Monto"])
    ws.append(["Marketing", 1200])
    out = io.BytesIO()
    wb.save(out)
    xlsx = extract_pages(out.getvalue(), XLSX)
    assert "Hoja: Presupuesto" in xlsx[0].text and "Marketing | 1200" in xlsx[0].text

    assert extract_pages(b"hola mundo", "text/plain")[0].text == "hola mundo"
    assert extract_pages(b"\x89PNG", "image/png") == []
    assert extract_pages(b"no es pdf", "application/pdf") == []


def test_fake_embedder_is_deterministic_and_semantic_enough() -> None:
    e = FakeEmbedder()
    a = e.embed_query("vacaciones del personal")
    assert a == e.embed_query("vacaciones del personal")
    related = e.embed_documents(["Política de vacaciones para el personal"])[0]
    unrelated = e.embed_documents(["Contrato de arriendo de bodega"])[0]
    assert _cos(a, related) > _cos(a, unrelated)
    assert abs(_cos(a, a) - 1.0) < 1e-6
