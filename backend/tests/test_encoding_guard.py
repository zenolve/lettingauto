"""Guard: double-encoded UTF-8 (mojibake) must never enter backend source.

A Windows encoding round-trip once corrupted source files by reading UTF-8
bytes as cp1252 and re-encoding them - e.g. the middle dot in offer names
became "A-circumflex middot", which a UAT tester saw rendered on the offer
dashboard ("the 'a' has a symbol on it").

This test scans every backend source/template file for the byte signatures
that corruption produces and fails the suite the moment one reappears, so a
bad-encoding edit breaks CI instead of shipping to users.

If this test fails: do NOT hand-edit the flagged characters. Re-run the
repair (`ftfy.fix_text` on the affected lines), and write any intentional
non-ASCII in Python string literals as \\uXXXX escapes instead.
"""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"

# UTF-8 output decoded as cp1252/latin-1 and re-encoded always starts a
# corrupted character with one of these byte prefixes ("A-circumflex" or
# "a-circumflex" followed by a re-encoded continuation byte). Legitimate
# English/legal text never contains these sequences.
MOJIBAKE_SIGNATURES = (
    b"\xc3\x82\xc2",  # corrupted U+00A0-U+00BF range: middot, pound, nbsp...
    b"\xc3\xa2\xc2",  # corrupted punctuation (dashes, quotes, ellipsis...)
    b"\xc3\xa2\xe2",  # doubly-corrupted punctuation (mojibake of mojibake)
)

SCANNED_SUFFIXES = {".py", ".html"}


def test_no_double_encoded_utf8_in_backend_source():
    offenders: list[str] = []
    for path in sorted(APP_ROOT.rglob("*")):
        if path.suffix not in SCANNED_SUFFIXES or not path.is_file():
            continue
        raw = path.read_bytes()
        for sig in MOJIBAKE_SIGNATURES:
            if sig in raw:
                offenders.append(f"{path.relative_to(APP_ROOT.parent)} contains {sig!r}")
                break
    assert not offenders, (
        "Double-encoded UTF-8 detected - an encoding-mangling edit corrupted "
        "these files (see this test's docstring for how to repair):\n  "
        + "\n  ".join(offenders)
    )
