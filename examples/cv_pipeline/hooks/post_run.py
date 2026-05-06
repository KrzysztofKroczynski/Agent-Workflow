from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Layout constants
_MARGIN = 20
_PAGE_W = 170  # usable width on A4 with 20mm margins
_ACCENT = (31, 73, 125)   # dark navy
_TEXT = (40, 40, 40)      # near-black
_MUTED = (110, 110, 110)  # gray


def run(ctx: Any, task: Any) -> None:
    final_cv = ctx.state.get("final_cv")
    if not final_cv:
        ctx.logger.warning("post_run: 'final_cv' not in context — skipping PDF export.")
        return

    try:
        from fpdf import FPDF, XPos, YPos  # noqa: F401
    except ImportError:
        ctx.logger.error("fpdf2 not installed. Run: uv sync")
        return

    output_dir = Path(ctx.workflow_root) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = ctx.state.get("output_filename") or "cv.pdf"
    output_path = output_dir / filename

    _render_pdf(final_cv, output_path)
    ctx.logger.info("CV PDF saved -> %s", output_path)


def _sanitize(text: str) -> str:
    """Replace non-latin-1 punctuation so Helvetica core font renders cleanly."""
    replacements = {
        "—": "-", "–": "-", "−": "-",  # dashes
        "•": "*", "·": "*",                   # bullets
        "“": '"', "”": '"',                   # smart quotes
        "‘": "'", "’": "'",                   # smart apostrophes
        "\\n": "\n",                                    # escaped newlines from JSON
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Drop anything still outside latin-1
    return text.encode("latin-1", errors="replace").decode("latin-1")


_YEAR_RE = re.compile(r"\d{4}")
_SECTION_HEADERS = {
    "professional summary", "summary", "work experience", "experience",
    "education", "skills", "technical skills", "certifications",
    "publications", "projects", "personal projects", "references",
    "languages", "awards",
}


def _classify(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    sl = s.lower().rstrip(":")
    if sl in _SECTION_HEADERS and s.endswith(":"):
        return "section"
    if s.startswith(("- ", "* ", "+ ")):
        return "bullet"
    if _YEAR_RE.search(s) and any(c in s for c in ["-", "–", "—", "("]):
        return "job_header"
    return "body"


def _render_pdf(text: str, path: Path) -> None:
    from fpdf import FPDF, XPos, YPos

    text = _sanitize(text)
    lines = text.splitlines()

    pdf = FPDF(format="A4")
    pdf.set_margins(_MARGIN, _MARGIN, _MARGIN)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=_MARGIN)

    # ── Parse contact block ──────────────────────────────────────────────────
    contact: dict[str, str] = {}
    body_start = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            body_start = i + 1
            break
        if ":" in s:
            key, _, val = s.partition(":")
            contact[key.strip().lower()] = val.strip()
            body_start = i + 1
        else:
            break

    name = contact.pop("name", "")
    contact_fields = list(contact.values())

    # ── Name ─────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 26)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 13, name, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    # ── Contact line ─────────────────────────────────────────────────────────
    if contact_fields:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.cell(0, 5, "  |  ".join(contact_fields),
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    # ── Thin rule under header ────────────────────────────────────────────────
    pdf.ln(3)
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.6)
    pdf.line(_MARGIN, pdf.get_y(), _MARGIN + _PAGE_W, pdf.get_y())
    pdf.ln(5)

    # ── Body ─────────────────────────────────────────────────────────────────
    for line in lines[body_start:]:
        kind = _classify(line)
        s = line.strip()

        if kind == "blank":
            pdf.ln(2)

        elif kind == "section":
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 10.5)
            pdf.set_text_color(*_ACCENT)
            pdf.set_x(_MARGIN)
            pdf.cell(0, 6, s.rstrip(":").upper(),
                     new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(*_ACCENT)
            pdf.set_line_width(0.3)
            y = pdf.get_y()
            pdf.line(_MARGIN, y, _MARGIN + _PAGE_W, y)
            pdf.set_x(_MARGIN)
            pdf.ln(3)

        elif kind == "bullet":
            pdf.set_font("Helvetica", "", 9.5)
            pdf.set_text_color(*_TEXT)
            pdf.set_x(_MARGIN + 4)
            pdf.cell(4, 5, "-", new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.multi_cell(_PAGE_W - 8, 5, s[2:], new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        elif kind == "job_header":
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*_TEXT)
            pdf.set_x(_MARGIN)
            pdf.multi_cell(0, 6, s, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        else:  # body
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*_TEXT)
            pdf.set_x(_MARGIN)
            pdf.multi_cell(0, 5.5, s, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.output(str(path))
