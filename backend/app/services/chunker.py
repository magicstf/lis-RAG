"""Recursive character splitter that keeps character offsets into the source text."""
from __future__ import annotations

from dataclasses import dataclass

from .parser import ParsedDocument

SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；"]


@dataclass
class ChunkPiece:
    seq: int
    content: str
    char_start: int
    char_end: int
    page_no: int | None
    section: str


def _split_pieces(text: str, base: int, chunk_size: int, separators: list[str]) -> list[tuple[int, int]]:
    """Return contiguous (start, end) pieces, each no longer than chunk_size when possible."""
    if len(text) <= chunk_size:
        return [(base, base + len(text))]
    if not separators:
        return [(base + i, base + min(i + chunk_size, len(text))) for i in range(0, len(text), chunk_size)]

    sep, rest = separators[0], separators[1:]
    if sep not in text:
        return _split_pieces(text, base, chunk_size, rest)

    pieces: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(text):
        idx = text.find(sep, cursor)
        if idx == -1:
            segment = text[cursor:]
            end = len(text)
        else:
            end = idx + len(sep)
            segment = text[cursor:end]
        if len(segment) > chunk_size:
            pieces.extend(_split_pieces(segment, base + cursor, chunk_size, rest))
        else:
            pieces.append((base + cursor, base + end))
        cursor = end
    return pieces


def _merge(pieces: list[tuple[int, int]], chunk_size: int, overlap: int) -> list[tuple[int, int]]:
    chunks: list[tuple[int, int]] = []
    window: list[tuple[int, int]] = []

    def window_len() -> int:
        return window[-1][1] - window[0][0] if window else 0

    for piece in pieces:
        piece_len = piece[1] - piece[0]
        if window and window_len() + piece_len > chunk_size:
            chunks.append((window[0][0], window[-1][1]))
            # keep trailing pieces for overlap
            kept: list[tuple[int, int]] = []
            total = 0
            for prev in reversed(window):
                length = prev[1] - prev[0]
                if total + length > overlap:
                    break
                kept.insert(0, prev)
                total += length
            window = kept
        window.append(piece)
    if window:
        chunks.append((window[0][0], window[-1][1]))
    return chunks


def split_document(doc: ParsedDocument, chunk_size: int, chunk_overlap: int) -> list[ChunkPiece]:
    text = doc.text
    if not text.strip():
        return []
    chunk_size = max(50, chunk_size)
    chunk_overlap = max(0, min(chunk_overlap, chunk_size - 1))
    pieces = _split_pieces(text, 0, chunk_size, SEPARATORS)
    spans = _merge(pieces, chunk_size, chunk_overlap)

    result: list[ChunkPiece] = []
    last_span: tuple[int, int] | None = None
    for start, end in spans:
        raw = text[start:end]
        stripped = raw.strip()
        if not stripped:
            continue
        lead = len(raw) - len(raw.lstrip())
        trail = len(raw) - len(raw.rstrip())
        s, e = start + lead, end - trail
        if last_span and (s, e) == last_span:
            continue
        last_span = (s, e)
        result.append(
            ChunkPiece(
                seq=len(result),
                content=text[s:e],
                char_start=s,
                char_end=e,
                page_no=doc.page_at(s),
                section=doc.section_at(s),
            )
        )
    return result
