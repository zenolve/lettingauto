"""One-shot extractor for the document library.

Reads the source .docx files from `~/Downloads` and writes their bodies out as
HTML under `backend/app/templates/library/`. Re-run whenever a source document
changes.

Strategy:
- ``.docx``  — uses **mammoth** to map Word styles → semantic HTML. This preserves
  heading hierarchy (Heading1/2/3 → ``<h1>/<h2>/<h3>``), numbered & bullet lists
  (Word's complex w:numId machinery → real ``<ol>`` / ``<ul>``), tables, runs
  (bold/italic/underline). The hand-rolled XML walker this replaces produced
  walls of ``<p>`` and dropped all clause numbering — see commit history.
- ``.doc``   (legacy binary) — antiword fallback, plain-text only. Tell the
  agent to save the file as .docx in Word and re-run; mammoth doesn't read
  the binary format and the antiword output is poor for legal contracts.

Add a new source: drop the .docx in ~/Downloads, append to ``SOURCE_FILES``,
re-run ``python -m scripts.extract_library_docs``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_FILES: dict[str, Path] = {
    # doc_id  -> source file on disk
    "pg_tcs_2026":   Path.home() / "Downloads" / "PG T and C's Final 2026(1).docx",
    "apt_pet_abnb":  Path.home() / "Downloads" / "APT Pet ABNB v3.0 Final (1).docx",
    "common_law_ta": Path.home() / "Downloads" / "Tenancy Agreement Common Law December 2020 (1).docx",
}


# Mammoth style map. Each line maps a Word paragraph style (LHS) to an HTML
# element (RHS). Unmapped styles fall through to <p>.
# Discovered styles in our actual contracts: Heading1, Title, Boldsubheading,
# Calibrisubheadinggreen, Paragraph, Parasubclause2, Schedule, Testimonium,
# Text, Untitledsubclause1/2/3. We collapse the various sub-clause/sub-heading
# styles into semantic equivalents so the editor renders a hierarchy the agent
# can follow.
MAMMOTH_STYLE_MAP = """
p[style-name='Title'] => h1.legal-title:fresh
p[style-name='Heading 1'] => h1:fresh
p[style-name='Heading1'] => h1:fresh
p[style-name='Heading 2'] => h2:fresh
p[style-name='Heading2'] => h2:fresh
p[style-name='Heading 3'] => h3:fresh
p[style-name='Heading3'] => h3:fresh
p[style-name='Schedule'] => h2.schedule:fresh
p[style-name='Boldsubheading'] => h3:fresh
p[style-name='Calibrisubheadinggreen'] => h4:fresh
p[style-name='Untitledsubclause1'] => p.subclause-1:fresh
p[style-name='Untitledsubclause2'] => p.subclause-2:fresh
p[style-name='Untitledsubclause3'] => p.subclause-3:fresh
p[style-name='Parasubclause2'] => p.subclause-2:fresh
p[style-name='Testimonium'] => p.testimonium:fresh
r[style-name='Bold'] => strong
r[style-name='Strong'] => strong
"""


def docx_to_html(path: Path) -> str:
    """Render a .docx via mammoth using the project style map.

    Mammoth handles numbered lists (`w:numId` references in the doc map back to
    `<ol>` / `<ul>` with the right nesting), so legal-clause numbering survives
    intact — that's the whole reason for this rewrite.
    """
    import mammoth  # local import — only the extractor script needs it

    with path.open("rb") as f:
        result = mammoth.convert_to_html(f, style_map=MAMMOTH_STYLE_MAP)
    for msg in result.messages:
        # Mammoth flags unmapped styles + unsupported features as warnings;
        # surface them so we know what's still being dropped.
        print(f"[mammoth-warn] {path.name}: {msg.message}", file=sys.stderr)
    return result.value


def doc_to_html(path: Path) -> str:
    """Last-resort fallback for legacy .doc binaries via antiword.

    The output is plain text — no tables, no styles, no list numbering. For
    legal contracts this is genuinely unusable; the script prints a warning
    so the user is told to save the file as .docx instead.
    """
    antiword = shutil.which("antiword")
    if not antiword:
        return (
            "<p><em>(Could not extract — antiword not installed. "
            "Save the .doc as .docx in Word and re-run the extractor.)</em></p>"
        )
    print(
        f"[warn] {path.name}: legacy .doc detected. Output will lose clause "
        f"numbering, tables, and merge fields. Save it as .docx and re-run.",
        file=sys.stderr,
    )
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
        print(f"[ok]   {doc_id}: {len(html)} chars -> {target}")


if __name__ == "__main__":
    main()
