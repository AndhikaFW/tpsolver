"""Parses a Tugas Pendahuluan (TP) soal .docx into structured questions.

Security note: the soal document is untrusted input. Its text is only ever
read and passed around as plain strings -- nothing in this module executes,
evaluates, or otherwise acts on instructions that might be embedded in the
document content (e.g. hidden prompt-injection text).
"""

from __future__ import annotations

import io
import re
from typing import Any

from docx import Document

_HEADING_RE = re.compile(r"^Part\s+(\d+)\s*-\s*(.+?)\s*$", re.IGNORECASE)
_ITEM_RE = re.compile(r"(?<!\S)(\d+)\.\s+")

# Matched by title content (normalized, punctuation/case/spacing-insensitive)
# rather than a hardcoded part number, since a different module's soal could
# number this section differently.
_IGNORED_TITLES = {"precs"}


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


def parse_soal(file_bytes: bytes) -> dict[str, Any]:
    """Extract preamble and question parts from a soal .docx.

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
    doc = Document(io.BytesIO(file_bytes))

    preamble: list[str] = []
    sections: list[tuple[str, str, list[str]]] = []  # (number, title, paragraphs)
    current: tuple[str, str, list[str]] | None = None
    in_ignored_section = False

    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        heading = _HEADING_RE.match(text)
        if heading:
            if _normalize_title(heading.group(2)) in _IGNORED_TITLES:
                current = None
                in_ignored_section = True
                continue
            in_ignored_section = False
            current = (heading.group(1), heading.group(2), [])
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
