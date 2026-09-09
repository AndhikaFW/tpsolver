"""Parses a Tugas Pendahuluan (TP) soal (.docx or .pdf) into structured
questions.

Security note: the soal document is untrusted input. Its text is only ever
read and passed around as plain strings -- nothing in this module executes,
evaluates, or otherwise acts on instructions that might be embedded in the
document content (e.g. hidden prompt-injection text).
"""

from __future__ import annotations

import io
import re
from typing import Any

import pdfplumber
from docx import Document

_ITEM_RE = re.compile(r"(?<!\S)(\d+)\.\s+")

# Matched by title content (normalized, punctuation/case/spacing-insensitive)
# rather than a hardcoded part number, since a different module's soal could
# number this section differently.
_IGNORED_TITLES = {"precs"}

_BULLET_RE = re.compile(r"^[•●*\-]\s+")

# Different modules' soal use different section-heading conventions -- e.g.
# "Part 1 - Teori" in one module, "I. SOAL" / "II. INSTALASI TOOLS" in
# another. Both are tried; whichever matches determines the part number.
_HEADING_RE = re.compile(r"^Part\s+(\d+)\s*-\s*(.+?)\s*$", re.IGNORECASE)
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_ROMAN_HEADING_RE = re.compile(r"^([IVXLC]+)\.\s*(.+?)\s*$")


def _roman_to_int(roman: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(roman):
        value = _ROMAN_VALUES[ch]
        total += -value if value < prev else value
        prev = max(prev, value)
    return total


def _match_heading(text: str) -> tuple[str, str] | None:
    """Returns (part_number, title) if `text` is a section heading, or None.

    Tries the "Part N - Title" convention first, then falls back to a
    standalone Roman-numeral convention ("I. Title", "II. Title", ...).
    """
    m = _HEADING_RE.match(text)
    if m:
        return m.group(1), m.group(2)
    m = _ROMAN_HEADING_RE.match(text)
    if m and m.group(2):
        return str(_roman_to_int(m.group(1))), m.group(2)
    return None


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _split_items(text: str) -> list[dict[str, Any]]:
    """Split a section's joined paragraph text into numbered question items.

    Items are marked by manual "N. " text at the start of a sentence (not
    Word's native numbered-list feature). A candidate match is only accepted
    when its digit equals the next expected item number (1, 2, 3, ...), so
    incidental "no. 1." style references inside a question's own body text
    are not mistaken for the start of a new item.
    """
    candidates = list(_ITEM_RE.finditer(text))
    accepted: list[tuple[int, int, int]] = []  # (number, text_start, match_start)
    expected = 1
    for m in candidates:
        number = int(m.group(1))
        if number == expected:
            accepted.append((number, m.end(), m.start()))
            expected += 1

    items: list[dict[str, Any]] = []
    for i, (number, start, _match_start) in enumerate(accepted):
        end = accepted[i + 1][2] if i + 1 < len(accepted) else len(text)
        item_text = text[start:end].strip()
        if item_text:
            items.append({"number": number, "text": item_text})
    return items


def _is_pdf(file_bytes: bytes) -> bool:
    return file_bytes.lstrip()[:4] == b"%PDF"


def _docx_paragraphs(file_bytes: bytes) -> list[str]:
    doc = Document(io.BytesIO(file_bytes))
    return [p.text for p in doc.paragraphs]


def _reflow_pdf_lines(lines: list[str]) -> list[str]:
    """Merges PDF lines that are just a mid-paragraph word-wrap back into the
    paragraph they belong to.

    PDF text extraction gives one entry per visual line, but a single logical
    paragraph in the source document usually reflows across several visual
    lines at PDF page width -- unlike .docx, where python-docx already gives
    one paragraph per logical block. A line only starts a new paragraph here
    if it looks like a heading, a bullet, or a numbered item; anything else is
    treated as a continuation of the previous line and joined with a space.

    A wrong guess here only affects cosmetic line breaks in the UI, not the
    item-splitting logic below -- that matches item markers directly in the
    joined text, not on paragraph boundaries.
    """
    paragraphs: list[str] = []
    for raw in lines:
        text = raw.strip()
        if not text:
            paragraphs.append("")
            continue
        starts_new = (
            not paragraphs
            or not paragraphs[-1]
            or _match_heading(text)
            or _ITEM_RE.match(text)
            or _BULLET_RE.match(text)
            or _match_heading(paragraphs[-1])  # never continue onto/after a heading line
        )
        if starts_new:
            paragraphs.append(text)
        else:
            paragraphs[-1] += f" {text}"
    return paragraphs


def _pdf_paragraphs(file_bytes: bytes) -> list[str]:
    """Extracts text from a PDF soal as a list of reconstructed paragraphs
    (see _reflow_pdf_lines). A heading such as "Part 1 - Teori" is only
    recognized below if it sits alone on its own visual line, same assumption
    already made for .docx paragraphs.
    """
    lines: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            lines.extend((page.extract_text() or "").split("\n"))
    paragraphs = _reflow_pdf_lines(lines)
    if not any(p.strip() for p in paragraphs):
        raise ValueError(
            "Tidak ada teks yang bisa dibaca dari PDF ini -- kemungkinan hasil scan gambar "
            "tanpa lapisan teks. Coba file .docx aslinya, atau PDF hasil export langsung dari "
            "Word/Google Docs."
        )
    return paragraphs


def parse_soal(file_bytes: bytes) -> dict[str, Any]:
    """Extract preamble and question parts from a soal .docx or .pdf.

    Sections whose title matches an ignored topic (currently "Pre-CS", which
    asks students to install tooling rather than answer anything) are dropped
    entirely -- they are never added to the returned parts, and their content
    is not treated as preamble either.

    Returns:
        {
          "preamble": [str, ...],
          "parts": {
            "1": {"title": str, "items": [{"number": int, "text": str}, ...]},
            "2": {...},
          },
        }
    """
    paragraphs = _pdf_paragraphs(file_bytes) if _is_pdf(file_bytes) else _docx_paragraphs(file_bytes)

    preamble: list[str] = []
    sections: list[tuple[str, str, list[str]]] = []  # (number, title, paragraphs)
    current: tuple[str, str, list[str]] | None = None
    in_ignored_section = False

    for raw_text in paragraphs:
        text = raw_text.strip()
        if not text:
            continue
        heading = _match_heading(text)
        if heading:
            number, title = heading
            if _normalize_title(title) in _IGNORED_TITLES:
                current = None
                in_ignored_section = True
                continue
            in_ignored_section = False
            current = (number, title, [])
            sections.append(current)
            continue
        if in_ignored_section:
            continue
        if current is None:
            preamble.append(text)
        else:
            current[2].append(text)

    parts: dict[str, Any] = {}
    for number, title, paragraphs in sections:
        joined = "\n".join(paragraphs)
        parts[number] = {"title": title, "items": _split_items(joined)}

    return {"preamble": preamble, "parts": parts}
