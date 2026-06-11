from datetime import date

from app.services.derivations import (
    derive_cert_status,
    derive_service_level,
    derive_tenancy_type,
    holding_deposit_deadline,
    is_overseas,
    next_april_5,
    nrl_withholding_active,
)


def test_cert_status_on_file():
    assert derive_cert_status("Yes", None) == "On File"


def test_cert_status_arranging():
    assert derive_cert_status("No", "Yes, arrange") == "Agency Arranging"


def test_cert_status_not_provided():
    assert derive_cert_status("No", "No") == "Not Provided"


def test_service_level_mappings():
    assert derive_service_level("Palace Gate Will Manage") == "Full Management"
    assert derive_service_level("I will Manage but PG collects rent") == "Rent Collection"
    assert derive_service_level("I will Manage") == "Let Only"
    assert derive_service_level("Other manages but PG collects rent") == "Rent Collection"
    assert derive_service_level("Other") == "Let Only"
    assert derive_service_level("") == "Let Only"


def test_tenancy_type_apt_central_london():
    assert derive_tenancy_type(50_000, "SW1A 1AA") == "APT"


def test_tenancy_type_is_postcode_independent():
    # Pure rent test since the 2026-05-16 correction — postcode is irrelevant
    # (Housing Act 1988 £100k threshold applies nationwide).
    assert derive_tenancy_type(50_000, "M1 1AA") == "APT"


def test_tenancy_type_high_rent_is_common_law():
    assert derive_tenancy_type(150_000, "SW1A 1AA") == "Common Law"


def test_nrl_active_when_overseas_and_no_number():
    assert nrl_withholding_active("Non-resident", None) is True


def test_nrl_inactive_when_number_present():
    assert nrl_withholding_active("Non-resident", "NRL1234") is False


def test_is_overseas():
    assert is_overseas("Non-resident") is True
    assert is_overseas("UK resident") is False


def test_holding_deposit_deadline_is_15_days_out():
    ref = date(2026, 1, 1)
    assert (holding_deposit_deadline(ref) - ref).days == 15


def test_next_april_5_after_april():
    assert next_april_5(date(2026, 5, 1)) == date(2027, 4, 5)


def test_next_april_5_before_april():
    assert next_april_5(date(2026, 3, 1)) == date(2026, 4, 5)
