"""HTML → PDF rendering for the contract editor.

Uses WeasyPrint so we get proper CSS support (page-break, headers, footers,
table-of-contents). The renderer wraps the contract body in the current
agency's branded shell defined in `templates/contracts/_shell.html`.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_DIR = Path(__file__).resolve().parent.parent / "templates" / "contracts"
_env = Environment(loader=FileSystemLoader(str(_DIR)), autoescape=select_autoescape(["html"]))


def render_contract_html(body_html: str, *, title: str, footer_text: str | None = None) -> str:
    """Wrap an editor body in the current agency's branded shell."""
    from app.core.branding import get_brand  # local import — avoid cycles
    b = get_brand()
    return _env.get_template("_shell.html").render(
        body_html=body_html,
        title=title,
        footer_text=footer_text or b.name,
        brand_navy=b.navy,
        brand_gold=b.gold,
        brand_name=b.name,
    )


def html_to_pdf(html: str) -> bytes:
    """Render the given HTML document to PDF bytes via WeasyPrint."""
    # Imported lazily so test runs that don't touch PDF don't pay the cost.
    from weasyprint import HTML  # type: ignore

    return HTML(string=html, base_url=str(_DIR)).write_pdf()


_CHROMIUM_WORKER = Path(__file__).resolve().parent / "_chromium_worker.py"


def html_to_pdf_chromium(html: str, *, timeout_s: int = 60) -> bytes:
    """Render HTML to PDF using headless Chromium (Playwright), via subprocess.

    Preferred renderer: Chromium is the same engine the editor preview uses,
    so the PDF is pixel-identical to the 'Preview in new tab' view — full CSS,
    table borders, fonts, the lot. Works on Windows without GTK/Pango.

    Runs in a SEPARATE Python subprocess (``_chromium_worker.py``) rather than
    in-process. This is the cross-platform fix: under uvicorn on Windows the
    event loop is a SelectorEventLoop, which can't spawn the Chromium child
    process; a fresh subprocess gets a ProactorEventLoop that can. On Linux it
    works either way, but the subprocess keeps one code path for both OSes and
    is safe to call from sync (PDF download) and async (send) routes alike.

    Raises if Playwright/Chromium isn't available or the render fails; callers
    fall back to WeasyPrint then fpdf2.
    """
    import subprocess  # lazy
    import sys
    import tempfile

    with tempfile.TemporaryDirectory(prefix="pg_pdf_") as td:
        td_path = Path(td)
        html_file = td_path / "doc.html"
        pdf_file = td_path / "doc.pdf"
        html_file.write_text(html, encoding="utf-8")

        proc = subprocess.run(
            [sys.executable, str(_CHROMIUM_WORKER), str(html_file), str(pdf_file)],
            capture_output=True,
            timeout=timeout_s,
        )
        if proc.returncode != 0 or not pdf_file.exists():
            stderr = proc.stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Chromium render failed (rc={proc.returncode}): {stderr}")
        return pdf_file.read_bytes()


def render_template_to_html(template_name: str, **ctx: Any) -> str:
    """Render one of the bundled contract templates with the given context."""
    from app.core.branding import get_brand  # local import — avoid cycles
    b = get_brand()
    return _env.get_template(template_name).render(
        brand_navy=b.navy,
        brand_gold=b.gold,
        brand_name=b.name,
        **ctx,
    )
