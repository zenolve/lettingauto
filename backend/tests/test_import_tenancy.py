"""Importing an already-running tenancy.

The design rule under test: an import is not a special record type. It creates
the same rows and is then walked through the same gates, so a tenancy only
reaches Live if its declared evidence actually satisfies the pipeline.
"""
import pytest
from pydantic import ValidationError

from app.handlers.pg_import import (
    IMPORT_DOCUMENT_CHECKLIST,
    TARGET_STAGE,
    _annual_rent,
    _tenancy_term,
)
from app.models.common import ImportTenancyInput
from app.routers.uploads import ALLOWED_BUCKETS

BASE = dict(
    address="99 Import Street", post_code="SW1A 9ZZ",
    landlord_full_name="Ivy Importer", landlord_email="ivy@example.com",
    tenants=[{"full_name": "Tom Tenant", "email": "tom@example.com", "is_lead": True}],
    rent_amount=1850, start_date="2025-09-01",
)


def test_document_checklist_buckets_are_uploadable():
    # A checklist entry naming a bucket the upload route rejects would give the
    # agent an uploader that 400s.
    for doc in IMPORT_DOCUMENT_CHECKLIST:
        assert doc["bucket"] in ALLOWED_BUCKETS, doc["bucket"]


def test_import_targets_live_not_end_of_tenancy():
    assert TARGET_STAGE == 8


def test_annual_rent_by_frequency():
    assert _annual_rent(1000, "Monthly") == 12000
    assert _annual_rent(1000, "Weekly") == 52000


def test_periodic_when_no_end_date():
    m = ImportTenancyInput(**BASE)
    assert _tenancy_term(m) == "Periodic"


def test_fixed_term_months_from_dates():
    m = ImportTenancyInput(**BASE, end_date="2026-08-31")
    assert _tenancy_term(m) == "12 months"


def test_tenancy_type_left_for_derivation():
    # Unset means "derive from the annualised rent" (Housing Act 1988 threshold),
    # exactly as take-on does - the importer shouldn't have to know the rule.
    assert ImportTenancyInput(**BASE).tenancy_type is None


def test_end_date_must_follow_start():
    with pytest.raises(ValidationError):
        ImportTenancyInput(**BASE, end_date="2025-08-01")


def test_at_least_one_tenant_required():
    payload = dict(BASE, tenants=[])
    with pytest.raises(ValidationError):
        ImportTenancyInput(**payload)


def test_running_tenancy_defaults_to_funds_cleared():
    # A tenancy that is already running has, by definition, had its money in.
    m = ImportTenancyInput(**BASE)
    assert m.funds_cleared is True
    assert m.works_signed_off is True


def test_signed_and_served_default_to_false():
    # Nothing is assumed about compliance: every assertion must be made
    # explicitly by the agent, so a lazy import cannot silently reach Live.
    m = ImportTenancyInput(**BASE)
    for field in ("tc_signed", "ta_landlord_signed", "ta_tenants_signed",
                  "how_to_rent_served", "gas_cert_served", "epc_served",
                  "eicr_served", "tds_info_served", "deposit_registered",
                  "tds_cert_on_file"):
        assert getattr(m, field) is False, field
