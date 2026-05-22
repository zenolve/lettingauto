"""Tally parser tests (spec §11.1)."""
from app.parsers.tally_parser import get_by_key, get_by_label, get_hidden, resolve_field


def test_label_match_text():
    fields = [{"label": "Property Address", "type": "INPUT_TEXT", "value": "11 Palace Gate"}]
    assert get_by_label(fields, "address") == "11 Palace Gate"


def test_key_match():
    fields = [{"key": "question_48Jzqk", "label": "X", "type": "INPUT_TEXT", "value": "v"}]
    assert get_by_key(fields, "question_48Jzqk") == "v"


def test_file_upload_returns_url():
    fields = [{
        "label": "EPC upload", "type": "FILE_UPLOAD",
        "value": [{"id": "1", "url": "https://example.com/x.pdf"}],
    }]
    assert get_by_label(fields, "epc upload") == "https://example.com/x.pdf"


def test_multiple_choice_resolves():
    fields = [{
        "label": "Service",
        "type": "MULTIPLE_CHOICE",
        "value": ["abc"],
        "options": [{"id": "abc", "text": "Full Management"}],
    }]
    assert get_by_label(fields, "service") == "Full Management"


def test_hidden_id():
    fields = [{"label": "id", "type": "HIDDEN_FIELDS", "value": "rec123"}]
    assert get_hidden(fields, "id") == "rec123"


def test_resolve_none():
    assert resolve_field({"type": "INPUT_TEXT", "value": ""}) is None
