"""APT (Assured Private Tenancy) validation — spec §5.4.1."""
from __future__ import annotations

from typing import Optional


def validate_apt(
    *,
    holding_deposit: Optional[float],
    weekly_rent: Optional[float],
    rent_in_advance_months: Optional[int],
    end_date: Optional[str],
) -> list[str]:
    """Return a list of human-readable violation messages (empty == valid)."""
    violations: list[str] = []

    if holding_deposit is not None and weekly_rent is not None and holding_deposit > weekly_rent:
        violations.append(
            f"Holding deposit £{holding_deposit:,.2f} exceeds 1 week rent "
            f"£{weekly_rent:,.2f}. Maximum permitted under Tenant Fees Act 2019."
        )

    if rent_in_advance_months is not None and rent_in_advance_months > 1:
        violations.append(
            f"Rent in advance {rent_in_advance_months} months exceeds 1 month "
            f"maximum for APT."
        )

    if end_date:
        violations.append(
            "APT should be periodic (no end date). End date set — confirm with agent."
        )

    return violations


def weekly_rent_from_monthly(monthly_rent: Optional[float]) -> Optional[float]:
    """Convert monthly rent to weekly rent using the 12 / 52 convention."""
    if monthly_rent is None:
        return None
    return (monthly_rent * 12) / 52
