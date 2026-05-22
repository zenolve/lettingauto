"""Standalone Chromium PDF worker — run as a subprocess by pdf_renderer.

Why a subprocess (cross-platform rationale):
  - Windows + uvicorn: the server runs on a SelectorEventLoop, which cannot
    spawn child processes. Playwright must launch the Chromium binary as a
    child process, so calling it in-process (even from a worker thread) raises
    NotImplementedError. A fresh Python subprocess gets the default Windows
    ProactorEventLoop, which supports subprocess spawning.
  - Linux: subprocess spawning works in-process too, but running through this
    same worker keeps the code path identical across platforms — no OS
    branching, no event-loop juggling.

Invoked as:
    python _chromium_worker.py <input_html_path> <output_pdf_path>

Reads the HTML file, renders to PDF via headless Chromium, writes the PDF.
Exits non-zero with a message on stderr if anything fails.
"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) != 3:
        sys.stderr.write("usage: _chromium_worker.py <input_html> <output_pdf>\n")
        return 2

    html_path, pdf_path = sys.argv[1], sys.argv[2]
    try:
        with open(html_path, encoding="utf-8") as f:
            html = f.read()
    except OSError as e:
        sys.stderr.write(f"cannot read html: {e}\n")
        return 3

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"playwright import failed: {e}\n")
        return 4

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            try:
                page = browser.new_page()
                # Self-contained HTML (data-URI images) → no real network, so
                # networkidle settles almost immediately.
                page.set_content(html, wait_until="networkidle")
                page.pdf(
                    path=pdf_path,
                    format="A4",
                    print_background=True,
                    margin={"top": "18mm", "bottom": "18mm", "left": "16mm", "right": "16mm"},
                )
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"render failed: {e}\n")
        return 5

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
