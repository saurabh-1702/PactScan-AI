"""The "clean" copy of a document version: every tracked change accepted.

The Fix & Learn Executor writes an approved edit as a *redline*: the old
wording struck through, an arrow, then the new wording underlined, all in one
paragraph. That is right for a reviewer, and useless as a contract to sign,
send, or feed back into Detect (the old wording is still in the text).

``make_clean_docx`` turns such a document into what the parties would actually
sign — the new wording only, no strike-through, no arrow — without touching
the stored version. Paragraphs that were never edited are left exactly as they
are, so the clean copy of v1 is simply v1.
"""

from __future__ import annotations

import io

from docx import Document
from docx.oxml.ns import qn

# The Executor's own separator between the struck old text and the new text.
_ARROW = "→"

_PREAMBLE_HEADING = "Reconstructed Contract"
_PREAMBLE_NOTE = "This document was reconstructed from structured clause extraction"


def _remove(run) -> None:
    run._element.getparent().remove(run._element)


def _accept_changes(paragraph) -> bool:
    """Drop the struck-through old text and the arrow, keep the new text as
    plain text. Returns True if the paragraph held a tracked change."""
    runs = list(paragraph.runs)
    for i in range(len(runs) - 1):
        old, sep = runs[i], runs[i + 1]
        if old.font.strike and sep.text.strip() == _ARROW:
            new = runs[i + 2] if i + 2 < len(runs) else None
            _remove(old)
            _remove(sep)
            if new is not None:
                rpr = new._element.rPr
                if rpr is not None:
                    for tag in ("w:u", "w:color"):
                        el = rpr.find(qn(tag))
                        if el is not None:
                            rpr.remove(el)
            return True
    return False


def _strip_synthesized_preamble(doc) -> None:
    """A PDF upload is stored as a .docx PactScan synthesized itself, with a
    title and an explanatory note at the top. Those describe the *file*, not the
    contract, so they must not be read back in as if they were clauses."""
    for paragraph in list(doc.paragraphs)[:4]:
        text = paragraph.text.strip()
        if text.startswith(_PREAMBLE_HEADING) or text.startswith(_PREAMBLE_NOTE):
            paragraph._element.getparent().remove(paragraph._element)


def make_clean_docx(docx_bytes: bytes, strip_preamble: bool = False) -> bytes:
    doc = Document(io.BytesIO(docx_bytes))
    for paragraph in doc.paragraphs:
        _accept_changes(paragraph)
    if strip_preamble:
        _strip_synthesized_preamble(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
