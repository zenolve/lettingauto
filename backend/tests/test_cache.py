"""Unit tests for the in-memory Airtable read cache (_TTLCache)."""
from app.db.airtable_client import _MISS, _TTLCache


def test_set_and_get():
    c = _TTLCache()
    c.set(("get", "properties", "rec1"), {"id": "rec1"}, ttl=10)
    assert c.get(("get", "properties", "rec1")) == {"id": "rec1"}


def test_missing_key_returns_sentinel():
    c = _TTLCache()
    assert c.get(("get", "properties", "nope")) is _MISS


def test_expired_entry_is_a_miss():
    c = _TTLCache()
    c.set(("all", "offers", None), [1, 2], ttl=-1)  # already expired
    assert c.get(("all", "offers", None)) is _MISS


def test_empty_list_is_a_hit_not_a_miss():
    # Critical: a legitimately-empty all_records result must be served from
    # cache, not re-fetched. The sentinel makes that distinguishable.
    c = _TTLCache()
    c.set(("all", "offers", None), [], ttl=10)
    assert c.get(("all", "offers", None)) == []


def test_invalidate_table_only_drops_that_table():
    c = _TTLCache()
    c.set(("all", "properties", None), [1], ttl=10)
    c.set(("get", "properties", "rec1"), {"x": 1}, ttl=10)
    c.set(("all", "offers", None), [2], ttl=10)
    dropped = c.invalidate_table("properties")
    assert dropped == 2
    assert c.get(("all", "properties", None)) is _MISS
    assert c.get(("get", "properties", "rec1")) is _MISS
    assert c.get(("all", "offers", None)) == [2]  # untouched


def test_clear():
    c = _TTLCache()
    c.set(("all", "x", None), [1], ttl=10)
    c.clear()
    assert c.get(("all", "x", None)) is _MISS
