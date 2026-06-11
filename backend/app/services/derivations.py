"""Pure functions that derive normalised values from raw form inputs."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Service level (spec §5.2.1)
# ---------------------------------------------------------------------------
_SERVICE_LEVEL_MAP = {
    # Current (agency-neutral) form labels
    "agency will manage": "Full Management",
    "i will manage but agency collects rent": "Rent Collection",
    "other manages but agency collects rent": "Rent Collection",
    # Legacy labels (pre-commercial forms / old Tally payloads)
    "palace gate will manage": "Full Management",
    "i will manage but pg collects rent": "Rent Collection",
    "other manages but pg collects rent": "Rent Collection",
    "i will manage": "Let Only",
    "other": "Let Only",
}


def derive_service_level(answer: Optional[str]) -> str:
    if not answer:
        return "Let Only"
    return _SERVICE_LEVEL_MAP.get(answer.strip().lower(), "Let Only")


# ---------------------------------------------------------------------------
# Certificate status (spec §5.2.2)
# ---------------------------------------------------------------------------
def derive_cert_status(has_cert: Optional[str], arrange: Optional[str]) -> str:
    """Return one of: 'On File', 'Agency Arranging', 'Not Provided'."""
    if has_cert and has_cert.lower().startswith("yes"):
        return "On File"
    if arrange and arrange.lower().startswith("yes"):
        return "Agency Arranging"
    return "Not Provided"


# ---------------------------------------------------------------------------
# Tenancy type — APT vs Common Law.
#
# Housing Act 1988 (as amended by Renters' Rights Act 2025): an Assured
# Periodic Tenancy applies when the annual rent does not exceed £100,000.
# Above that threshold the tenancy falls outside the Housing Act and is
# treated as a common-law contractual tenancy.
#
# Postcode is irrelevant to the determination — it's a pure rent test.
# (Earlier versions of this function gated APT on central-London postcodes,
# which incorrectly classified most ≤£100k tenancies as Common Law. Bug
# corrected on 2026-05-16.)
# ---------------------------------------------------------------------------
APT_RENT_THRESHOLD = 100_000


def derive_tenancy_type(annual_rent: Optional[float], postcode: Optional[str] = None) -> str:
    # `postcode` kept in the signature for backwards-compatibility but no
    # longer used. Callers can pass it or omit it.
    del postcode
    if annual_rent is None:
        # No rent on file → can't determine; default to APT (the safer assumption
        # under RRA 2025 — APT is the modern norm for ≤£100k London lets).
        return "APT"
    return "APT" if annual_rent <= APT_RENT_THRESHOLD else "Common Law"


# ---------------------------------------------------------------------------
# NRL / residency derivations
# ---------------------------------------------------------------------------
def is_overseas(residency: Optional[str]) -> bool:
    if not residency:
        return False
    r = residency.lower()
    return "non" in r or "overseas" in r


def nrl_withholding_active(residency: Optional[str], approval_number: Optional[str]) -> bool:
    return is_overseas(residency) and not (approval_number or "").strip()


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
def parse_iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except Exception:
            return None


def next_april_5(reference: Optional[date] = None) -> date:
    """Next 5 April after the reference date (HMRC tax year end)."""
    ref = reference or date.today()
    candidate = date(ref.year, 4, 5)
    if candidate <= ref:
        candidate = date(ref.year + 1, 4, 5)
    return candidate


def holding_deposit_deadline(reference: Optional[date] = None) -> date:
    """Tenant Fees Act 2019 deadline: 15 days from today."""
    from datetime import timedelta
    return (reference or date.today()) + timedelta(days=15)
