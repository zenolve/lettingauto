"""One-shot extractor for the document library.

Reads the source .docx / .doc files from `~/Downloads` and writes their bodies
out as HTML under `backend/app/templates/library/`. Re-run whenever a source
document changes.

Strategy:
- .docx -&gt; parse `word/document.xml` directly (paragraphs + tables). No external
  dep beyond stdlib.
- .doc  -&gt; call out to antiword if available, otherwise leave a stub.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

SOURCE_FILES: dict[str, Path] = {
    # doc_id -&gt; source file on disk
    "pg_tcs_2026":   Path.home() / "Downloads" / "PG T and C's Final 2026(1).docx",
    "apt_pet_abnb":  Path.home() / "Downloads" / "APT Pet ABNB v3.0 Final.docx",
    "common_law_ta": Path.home() / "Downloads" / "Tenancy Agreement Common Law December 2020(1).doc",
}


def _para_text(el) -> str:
    parts: list[str] = []
    for t in el.iter(f"{{{NS['w']}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def docx_to_html(path: Path) -> str:
    """Render a .docx body to a minimal HTML string.

    Paragraphs become <p>, tables become <table>. Bold runs preserved.
    No images, no styles beyond bold — enough for an editor to load and the
    user to tweak.
    """
    with zipfile.ZipFile(path) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    body = tree.getroot().find(f"{{{NS['w']}}}body")
    if body is None:
        return ""

    lines: list[str] = []
    for child in body:
        tag = child.tag.split("}", 1)[-1]
        if tag == "p":
            txt = _para_text(child)
            if not txt.strip():
                lines.append("<p>&nbsp;</p>")
            else:
                # Promote ALL-CAPS short paragraphs to headings — keeps the
                # editor readable without parsing every w:pStyle.
                stripped = txt.strip()
                if len(stripped) < 80 and stripped == stripped.upper() and any(c.isalpha() for c in stripped):
                    lines.append(f"<h3>{stripped}</h3>")
                else:
                    lines.append(f"<p>{stripped}</p>")
        elif tag == "tbl":
            lines.append("<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse;width:100%;margin:8px 0;'>")
            for row in child.findall(f"{{{NS['w']}}}tr"):
                cells = [_para_text(c).strip() for c in row.findall(f"{{{NS['w']}}}tc")]
                lines.append("<tr>" + "".join(f"<td style='vertical-align:top;'>{c or '&nbsp;'}</td>" for c in cells) + "</tr>")
            lines.append("</table>")
    return "\n".join(lines)


def doc_to_html(path: Path) -> str:
    """Render a legacy .doc file via antiword. Falls back to a stub if missing."""
    antiword = shutil.which("antiword")
    if not antiword:
        return "<p><em>(Could not extract — antiword not installed. Install antiword or save the .doc as .docx to import.)</em></p>"
    try:
        text = subprocess.check_output(
            [antiword, "-w", "100", str(path)],
            text=True, encoding="utf-8", errors="replace",
        )
    except subprocess.CalledProcessError as e:
        return f"<p><em>(antiword failed: {e})</em></p>"

    out: list[str] = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        stripped = para.replace("\n", " ").strip()
        if len(stripped) < 80 and stripped == stripped.upper() and any(c.isalpha() for c in stripped):
            out.append(f"<h3>{stripped}</h3>")
        else:
            out.append(f"<p>{stripped}</p>")
    return "\n".join(out)


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "app" / "templates" / "library"
    out_dir.mkdir(parents=True, exist_ok=True)

    for doc_id, src in SOURCE_FILES.items():
        if not src.exists():
            print(f"[skip] {doc_id}: source not found ({src})", file=sys.stderr)
            continue
        suffix = src.suffix.lower()
        if suffix == ".docx":
            html = docx_to_html(src)
        elif suffix == ".doc":
            html = doc_to_html(src)
        else:
            print(f"[skip] {doc_id}: unsupported suffix {suffix}", file=sys.stderr)
            continue
        target = out_dir / f"{doc_id}.html"
        target.write_text(html, encoding="utf-8")
        print(f"[ok]   {doc_id}: {len(html)} chars -&gt; {target}")


if __name__ == "__main__":
    main()
