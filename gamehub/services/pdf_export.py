"""Plain-text → PDF export used by the Developer file browser.

Lets an admin tap "📑 PDF qilib yuklash" after reading any project file
(code, config, docs — anything the GitHub provider can read as text) and
receive it back as a paginated, monospace PDF document in Telegram.

Kept intentionally dependency-light: reportlab's built-in Courier/Helvetica
fonts only support Latin-1, so every line is sanitised before drawing —
any character outside that range is replaced rather than raising.
"""

from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_MARGIN = 15 * mm
_FONT = "Courier"
_FONT_SIZE = 8
_LINE_HEIGHT = _FONT_SIZE + 2.4
_TITLE_FONT_SIZE = 12


def _sanitize(line: str) -> str:
    """Keep the PDF from crashing on characters outside Latin-1."""
    return line.encode("latin-1", errors="replace").decode("latin-1")


def _wrap_lines(text: str, chars_per_line: int) -> list[str]:
    wrapped: list[str] = []
    for raw_line in text.splitlines() or [""]:
        raw_line = _sanitize(raw_line).rstrip("\r")
        if not raw_line:
            wrapped.append("")
            continue
        while len(raw_line) > chars_per_line:
            wrapped.append(raw_line[:chars_per_line])
            raw_line = raw_line[chars_per_line:]
        wrapped.append(raw_line)
    return wrapped


def text_to_pdf_bytes(text: str, title: str) -> bytes:
    """Render ``text`` as a paginated monospace PDF and return raw bytes."""
    buf = io.BytesIO()
    page_w, page_h = A4
    c = canvas.Canvas(buf, pagesize=A4)

    usable_w = page_w - 2 * _MARGIN
    # Courier is a fixed-width font — ~0.6 * font size per character.
    chars_per_line = max(40, int(usable_w / (_FONT_SIZE * 0.6)))
    lines = _wrap_lines(text, chars_per_line)

    def _draw_header(page_num: int) -> float:
        c.setFont("Helvetica-Bold", _TITLE_FONT_SIZE)
        c.drawString(_MARGIN, page_h - _MARGIN, _sanitize(title)[:90])
        c.setFont("Helvetica", 7)
        c.drawRightString(page_w - _MARGIN, page_h - _MARGIN, f"{page_num}-bet")
        c.setFont(_FONT, _FONT_SIZE)
        return page_h - _MARGIN - _LINE_HEIGHT * 2

    page_num = 1
    y = _draw_header(page_num)
    for line in lines:
        if y < _MARGIN:
            c.showPage()
            page_num += 1
            y = _draw_header(page_num)
        c.drawString(_MARGIN, y, line)
        y -= _LINE_HEIGHT

    c.save()
    return buf.getvalue()
