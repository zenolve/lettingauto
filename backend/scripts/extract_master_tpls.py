"""Carve every TPL-XX template body out of the master Palace Gate doc.

The master ``PG_Master_v2_final.docx`` is structured as a single long Word
file in which each correspondence template starts with a paragraph whose
text is exactly ``TPL-XX  <Name>`` (a marker the master author maintains).
Everything between one such marker and the next belongs to that TPL.

This script walks the .docx body once, accumulates paragraphs per TPL,
substitutes the master's ``[Bracketed]`` placeholders for our merge tokens
(``{{landlord_full_name}}`` etc), and writes each TPL out as an HTML file
under ``backend/app/templates/library/`` named after the catalog id.

Re-run any time the master doc changes.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

MASTER = Path.home() / "Downloads" / "PG_Master_v2_final.docx"
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "templates" / "library"

# Catalog of TPL → library id. Mirrors the ids in
# app/services/document_library.py so each extracted body slots in without
# code changes. Subletters (35a/b/c) get distinct ids; the rest follow the
# simple "tpl_NN" convention.
TPL_IDS: dict[str, str] = {
    "TPL-01": "tpl_01", "TPL-02": "tpl_02", "TPL-03": "tpl_03",
    "TPL-04": "tpl_04", "TPL-05": "tpl_05", "TPL-06": "tpl_06",
    "TPL-07": "tpl_07", "TPL-08": "tpl_08", "TPL-09": "tpl_09",
    "TPL-10": "tpl_10", "TPL-11": "tpl_11", "TPL-12": "tpl_12",
    "TPL-13": "tpl_13", "TPL-14": "tpl_14", "TPL-15": "tpl_15",
    "TPL-16": "tpl_16", "TPL-17": "tpl_17", "TPL-18": "tpl_18",
    "TPL-19": "tpl_19", "TPL-20": "tpl_20", "TPL-21": "tpl_21",
    "TPL-22": "tpl_22", "TPL-23": "tpl_23", "TPL-24": "tpl_24",
    "TPL-25": "tpl_25", "TPL-26": "tpl_26", "TPL-27": "tpl_27",
    "TPL-28": "tpl_28", "TPL-29": "tpl_29", "TPL-30": "tpl_30",
    "TPL-31": "tpl_31", "TPL-32": "tpl_32", "TPL-33": "tpl_33",
    "TPL-34": "tpl_34",
    "TPL-35a": "tpl_35a", "TPL-35b": "tpl_35b", "TPL-35c": "tpl_35c",
    "TPL-36": "tpl_36", "TPL-37": "tpl_37", "TPL-38": "tpl_38",
    "TPL-39": "tpl_39", "TPL-40": "tpl_40", "TPL-41": "tpl_41",
    "TPL-42": "tpl_42",
}

# Master-doc placeholder → our merge-field token. Keys are the literal strings
# the master author types between square brackets. Extend this map when new
# placeholders show up.
MERGE_MAP: dict[str, str] = {
    "Date":                    "today",
    "Landlord Name":           "landlord_full_name",
    "Landlord name":           "landlord_full_name",
    "Property Address":        "property_address",
    "Property address":        "property_address",
    "Tenant Name":             "tenant_full_name",
    "Tenant name":             "tenant_full_name",
    "Tenant Email":            "tenant_email",
    "Landlord Email":          "landlord_email",
    "Start Date":              "tenancy_start_date",
    "End Date":                "tenancy_end_date",
    "Rent":                    "monthly_rent",
    "Monthly Rent":            "monthly_rent",
    "Deposit":                 "deposit_amount",
    "Service Level":           "service_level",
    "Tenancy Type":            "tenancy_type",
}


def _para_text(el) -> str:
    parts: list[str] = []
    for t in el.iter(f"{{{NS['w']}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _para_is_bold(el) -> bool:
    # Heuristic: if the paragraph has at least one bold run, treat as heading.
    for rPr in el.iter(f"{{{NS['w']}}}rPr"):
        if rPr.find(f"{{{NS['w']}}}b") is not None:
            return True
    return False


_TPL_RE = re.compile(r"^\s*(TPL-\d+[a-z]?)\b", re.IGNORECASE)


def _bracket_subst(text: str) -> str:
    """Replace [Foo] occurrences with {{merge_field}} when known.

    Unknown brackets stay as-is so the agent can see them in the editor.
    """
    def repl(m: re.Match) -> str:
        raw = m.group(1).strip()
        key = MERGE_MAP.get(raw)
        if key:
            return "{{" + key + "}}"
        # Fallback: snake-case the bracket label so the agent can still wire it
        # via a custom merge field if desired.
        snake = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
        return "[" + raw + "]"  # unchanged when we can't map it cleanly
    return re.sub(r"\[([^\[\]]{1,80})\]", repl, text)


def _html_for_para(text: str, is_heading: bool) -> str:
    text = _bracket_subst(text.strip())
    if not text:
        return "<p>&nbsp;</p>"
    if is_heading and len(text) < 120:
        return f"<h3>{text}</h3>"
    return f"<p>{text}</p>"


def main() -> None:
    if not MASTER.exists():
        print(f"ERROR: master doc not found at {MASTER}", file=sys.stderr)
        sys.exit(1)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(MASTER) as z:
        with z.open("word/document.xml") as f:
            tree = ET.parse(f)
    body = tree.getroot().find(f"{{{NS['w']}}}body")
    if body is None:
        print("ERROR: master doc body is empty", file=sys.stderr)
        sys.exit(1)

    # Walk body paragraphs; partition into TPL sections on the TPL-XX marker.
    sections: list[tuple[str, list[str]]] = []  # [(tpl_id_marker, [html lines])]
    current_id: str | None = None
    current_lines: list[str] = []
    skip_master_preamble = True

    for child in body:
        tag = child.tag.split("}", 1)[-1]
        if tag != "p":
            # Tables: flatten as <table> inside the current section. Skip if
            # we're still in the preamble.
            if current_id and tag == "tbl":
                rows: list[str] = []
                for row in child.findall(f"{{{NS['w']}}}tr"):
                    cells = [_bracket_subst(_para_text(c).strip()) for c in row.findall(f"{{{NS['w']}}}tc")]
                    rows.append("<tr>" + "".join(f"<td style='vertical-align:top;padding:4px;border:1px solid #ccc;'>{c or '&nbsp;'}</td>" for c in cells) + "</tr>")
                if rows:
                    current_lines.append(
                        "<table style='border-collapse:collapse;width:100%;margin:8px 0;'>" + "".join(rows) + "</table>"
                    )
            continue

        text = _para_text(child)
        m = _TPL_RE.match(text)
        if m:
            marker = m.group(1).upper().replace("TPL-", "TPL-")
            # Normalise case for subletters (TPL-35A → TPL-35a)
            if marker[-1].isalpha():
                marker = marker[:-1] + marker[-1].lower()
            # close previous
            if current_id:
                sections.append((current_id, current_lines))
            current_id = marker
            current_lines = []
            skip_master_preamble = False
            continue

        if skip_master_preamble or current_id is None:
            continue

        # Stop if we hit the "PART 1" / "PART 2" header marking end-of-templates
        if text.strip().upper().startswith("PART 1  |") or text.strip().upper().startswith("PALACE GATE  |"):
            if current_id:
                sections.append((current_id, current_lines))
                current_id = None
            continue

        current_lines.append(_html_for_para(text, is_heading=_para_is_bold(child)))

    # tail flush
    if current_id:
        sections.append((current_id, current_lines))

    # Write each section
    written = 0
    skipped: list[str] = []
    for marker, lines in sections:
        doc_id = TPL_IDS.get(marker)
        if not doc_id:
            skipped.append(marker)
            continue
        # Trim leading blank paragraphs
        while lines and lines[0] in ("<p>&nbsp;</p>", ""):
            lines.pop(0)
        while lines and lines[-1] in ("<p>&nbsp;</p>", ""):
            lines.pop()
        if not lines:
            skipped.append(marker)
            continue
        out_path = OUT_DIR / f"{doc_id}.html"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        written += 1
        print(f"[ok]   {marker} -> {out_path.name}  ({len(out_path.read_text(encoding='utf-8'))} chars)")

    print(f"\nWritten: {written}; skipped: {skipped}")


if __name__ == "__main__":
    main()
