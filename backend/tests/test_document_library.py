"""The document library catalogue and the template files behind it.

Guards the two things that silently break a send: a catalogue entry whose
body file is missing (the editor shows a placeholder and the agent emails
it), and a template token that no longer exists in the merge-field catalogue
(it prints literally - "{{tenant_full_name}}" and all - in a letter a tenant
receives).
"""
import re

from app.routers import library as library_router
from app.services.document_library import _LIBRARY_DIR, get_body, get_document, list_documents
from app.services.merge_fields import MERGE_FIELD_CATALOGUE

TOKEN = re.compile(r"{{\s*([a-z_]+)\s*}}")
CATALOGUE_KEYS = {m["key"] for m in MERGE_FIELD_CATALOGUE}


def test_every_library_file_entry_has_a_body_on_disk():
    for doc in list_documents():
        if doc.source == "library_file":
            assert doc.body_file and (_LIBRARY_DIR / doc.body_file).stat().st_size > 0, doc.id


def test_every_template_token_exists_in_the_merge_catalogue():
    missing = {}
    for path in sorted(_LIBRARY_DIR.glob("*.html")):
        unknown = set(TOKEN.findall(path.read_text(encoding="utf-8"))) - CATALOGUE_KEYS
        if unknown:
            missing[path.name] = sorted(unknown)
    assert missing == {}


def test_tenant_acceptance_letter_is_registered_beside_the_landlord_one():
    doc = get_document("tpl_43")
    assert doc is not None
    assert (doc.stage, doc.default_mode, doc.source) == (4, "email_pdf", "library_file")
    assert doc.audience == ["Tenant"]
    landlord = get_document("tpl_05")
    assert landlord is not None and landlord.stage == 4 and landlord.audience == []


def test_tenant_acceptance_letter_is_fully_tokenised_and_unbranded():
    body = get_body(get_document("tpl_43"))
    assert "[" not in body, "leftover [bracket] placeholder"
    assert "Palace Gate" not in body and "PALACE GATE" not in body
    for key in ("tenant_full_name", "tenancy_start_date", "monthly_rent", "deposit_amount",
                "tenancy_term", "special_conditions", "brand_name"):
        assert "{{" + key + "}}" in body, key


def test_audience_defaults_from_catalogue_until_set(tmp_path, monkeypatch):
    monkeypatch.setattr(library_router, "_audience_path", lambda: tmp_path / "doc_audience.json")
    assert library_router.get_audience("tpl_43") == ["Tenant"]    # no file yet: catalogue default
    assert library_router.get_audience("tpl_05") == []
    library_router.set_audience("tpl_43", ["Landlord"])
    assert library_router.get_audience("tpl_43") == ["Landlord"]  # explicit override wins
    library_router.set_audience("tpl_43", [])
    assert library_router.get_audience("tpl_43") == []            # explicit "nobody" wins too
