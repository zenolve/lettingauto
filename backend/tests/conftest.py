"""Shared fixtures.

``fake_db`` swaps the Supabase adapter for ``tests.fake_supabase.FakeSupabase``
so handler tests can run the real write path - rows, links, gate walk -
without a database. Stages 1-9 are pre-seeded because every gate walk looks
them up.
"""
import pytest

from tests.fake_supabase import FakeSupabase


@pytest.fixture
def fake_db(monkeypatch) -> FakeSupabase:
    fake = FakeSupabase()
    fake.install(monkeypatch)
    fake.seed_stages()
    return fake
