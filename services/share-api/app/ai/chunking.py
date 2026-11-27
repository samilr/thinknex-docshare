"""Fragmentación para RAG: ~N tokens por fragmento, con solape, respetando párrafos.

Los tokens se estiman por palabras (≈1,35 tokens por palabra en español): suficiente para
dimensionar fragmentos sin depender de un tokenizador.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ai.extract import PageText

_TOKENS_PER_WORD = 1.35
_SENTENCE = re.compile(r"(?<=[.!?;:])\s+")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    page_from: int
    page_to: int


def estimate_tokens(text: str) -> int:
    return int(len(text.split()) * _TOKENS_PER_WORD) + 1


def _pieces(page: PageText, max_tokens: int) -> list[tuple[int, str]]:
    """Párrafos de la página; los muy largos se parten por oraciones y, si hace falta, palabras."""
    pieces: list[tuple[int, str]] = []
    for paragraph in re.split(r"\n\s*\n", page.text):
        paragraph = " ".join(paragraph.split())
        if not paragraph:
            continue
        if estimate_tokens(paragraph) <= max_tokens:
            pieces.append((page.page, paragraph))
            continue
        for sentence in _SENTENCE.split(paragraph):
            words = sentence.split()
            step = max(1, int(max_tokens / _TOKENS_PER_WORD))
            for start in range(0, len(words), step):
                pieces.append((page.page, " ".join(words[start : start + step])))
    return pieces


def chunk_pages(pages: list[PageText], max_tokens: int = 700, overlap: int = 80) -> list[Chunk]:
    pieces = [piece for page in pages for piece in _pieces(page, max_tokens)]
    chunks: list[Chunk] = []
    current: list[tuple[int, str]] = []
    size = 0
    for piece in pieces:
        tokens = estimate_tokens(piece[1])
        if current and size + tokens > max_tokens:
            chunks.append(_make(len(chunks), current))
            # Solape: se arrastran los últimos trozos hasta ~overlap tokens.
            carried: list[tuple[int, str]] = []
            carried_size = 0
            for previous in reversed(current):
                t = estimate_tokens(previous[1])
                if carried_size + t > overlap:
                    break
                carried.insert(0, previous)
                carried_size += t
            current, size = carried, carried_size
        current.append(piece)
        size += tokens
    if current:
        chunks.append(_make(len(chunks), current))
    return chunks


def _make(index: int, pieces: list[tuple[int, str]]) -> Chunk:
    return Chunk(
        index=index,
        text="\n\n".join(text for _, text in pieces),
        page_from=pieces[0][0],
        page_to=pieces[-1][0],
    )
