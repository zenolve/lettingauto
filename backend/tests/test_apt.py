from app.services.apt import validate_apt, weekly_rent_from_monthly


def test_holding_deposit_violation():
    weekly = weekly_rent_from_monthly(2000)  # ≈ £461.54
    violations = validate_apt(
        holding_deposit=500.0,
        weekly_rent=weekly,
        rent_in_advance_months=1,
        end_date=None,
    )
    assert any("Holding deposit" in v for v in violations)


def test_rent_in_advance_violation():
    weekly = weekly_rent_from_monthly(2000)
    violations = validate_apt(
        holding_deposit=400.0,
        weekly_rent=weekly,
        rent_in_advance_months=3,
        end_date=None,
    )
    assert any("Rent in advance" in v for v in violations)


def test_end_date_flag():
    weekly = weekly_rent_from_monthly(2000)
    violations = validate_apt(
        holding_deposit=400.0,
        weekly_rent=weekly,
        rent_in_advance_months=1,
        end_date="2027-12-31",
    )
    assert any("periodic" in v.lower() for v in violations)


def test_valid_apt_no_violations():
    weekly = weekly_rent_from_monthly(2000)
    assert validate_apt(holding_deposit=400, weekly_rent=weekly,
                        rent_in_advance_months=1, end_date=None) == []
