"""Document parsing: turns an uploaded file into plain text plus page / section spans."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from ..errors import UnprocessableFile

SUPPORTED_TYPES = {"pdf", "docx", "md", "txt"}


@dataclass
class Span:
    start: int
    end: int
    label: int | str


@dataclass
class ParsedDocument:
    text: str
    pages: list[Span] = field(default_factory=list)      # label = page_no (1-based)
    sections: list[Span] = field(default_factory=list)   # label = section title path

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    def page_at(self, pos: int) -> int | None:
        for span in self.pages:
            if span.start <= pos < span.end:
                return int(span.label)
        if self.pages and pos >= self.pages[-1].end:
            return int(self.pages[-1].label)
        return None

    def section_at(self, pos: int) -> str:
        for span in self.sections:
            if span.start <= pos < span.end:
                return str(span.label)
        return ""


def detect_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_TYPES:
        raise UnprocessableFile("仅支持 .pdf / .docx / .md / .txt 文件", detail={"filename": filename})
    return ext


def check_magic(file_type: str, data: bytes) -> None:
    if file_type == "pdf" and not data.lstrip()[:4].startswith(b"%PDF"):
        raise UnprocessableFile("文件不是有效的 PDF（文件头缺少 %PDF）")
    if file_type == "docx" and not data[:2] == b"PK":
        raise UnprocessableFile("文件不是有效的 DOCX（缺少 ZIP 文件头）")


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise UnprocessableFile("文本文件无法按 UTF-8 或 GBK 解码")


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_pdf(data: bytes) -> ParsedDocument:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:  # pragma: no cover - depends on file
                raise UnprocessableFile("PDF 已加密，无法读取", detail=str(exc)) from exc
        parts: list[str] = []
        pages: list[Span] = []
        cursor = 0
        for idx, page in enumerate(reader.pages, start=1):
            page_text = _normalize(page.extract_text() or "")
            if parts:
                parts.append("\n")
                cursor += 1
            start = cursor
            parts.append(page_text)
            cursor += len(page_text)
            pages.append(Span(start, cursor, idx))
        return ParsedDocument(text="".join(parts), pages=pages)
    except UnprocessableFile:
        raise
    except Exception as exc:
        raise UnprocessableFile("PDF 文件无法打开或已损坏", detail=f"{type(exc).__name__}: {exc}") from exc


def _parse_docx(data: bytes) -> ParsedDocument:
    try:
        import docx

        document = docx.Document(io.BytesIO(data))
        paragraphs = [_normalize(p.text) for p in document.paragraphs]
        return ParsedDocument(text="\n".join(paragraphs))
    except Exception as exc:
        raise UnprocessableFile("DOCX 文件无法打开或已损坏", detail=f"{type(exc).__name__}: {exc}") from exc


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def _parse_markdown(data: bytes) -> ParsedDocument:
    text = _normalize(_decode_text(data))
    sections: list[Span] = []
    path: list[tuple[int, str]] = []
    current_start = 0
    current_label = ""
    offset = 0
    for line in text.split("\n"):
        match = _HEADING_RE.match(line)
        if match:
            if offset > current_start:
                sections.append(Span(current_start, offset, current_label))
            level = len(match.group(1))
            title = match.group(2).strip()
            path = [(lvl, t) for lvl, t in path if lvl < level]
            path.append((level, title))
            current_label = " > ".join(t for _, t in path)
            current_start = offset
        offset += len(line) + 1
    sections.append(Span(current_start, len(text), current_label))
    return ParsedDocument(text=text, sections=sections)


def _parse_txt(data: bytes) -> ParsedDocument:
    return ParsedDocument(text=_normalize(_decode_text(data)))


def parse_document(file_type: str, data: bytes) -> ParsedDocument:
    if file_type == "pdf":
        return _parse_pdf(data)
    if file_type == "docx":
        return _parse_docx(data)
    if file_type == "md":
        return _parse_markdown(data)
    if file_type == "txt":
        return _parse_txt(data)
    raise UnprocessableFile("不支持的文件类型", detail={"file_type": file_type})
