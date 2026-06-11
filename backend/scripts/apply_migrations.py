"""Apply every SQL file in ``supabase/migrations/`` to the configured database.

Targets whatever ``SUPABASE_DB_URL`` points at — the local dev Postgres or a
real Supabase project (Settings → Database → Connection string, session
pooler). Files are applied in lexical order (``001_…`` then ``002_…``) inside
one transaction each, so a failure rolls that file back cleanly.

Run from ``backend/``:

    python -m scripts.apply_migrations            # apply, then verify
    python -m scripts.apply_migrations --verify   # just print the current schema

This is an alternative to the Supabase MCP server / SQL editor for applying the
schema; the resulting tables are identical. For a brand-new project run it
once. It is NOT idempotent (the DDL uses bare ``create table``), so re-running
against a populated database will error on the first existing object — that's
the intended "already applied" signal, not data loss.
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.config import settings

_MIGRATIONS = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations"

_EXPECTED_TABLES = 29  # 13 entity + 16 junctions (001) ... + agencies/agency_users (002)


def _connect():
    if not settings.supabase_db_url:
        raise SystemExit("SUPABASE_DB_URL is not set — point it at your Supabase project first.")
    import psycopg  # local import — runtime only
    # autocommit=True: each migration file carries its own begin;/commit;, so
    # the file's transaction controls atomicity. A failure mid-file aborts that
    # file's transaction server-side (nothing partial is committed).
    return psycopg.connect(settings.supabase_db_url, autocommit=True)


def _safe_host(url: str) -> str:
    # Print where we're applying WITHOUT leaking the password.
    try:
        tail = url.split("@", 1)[1]
    except IndexError:
        tail = url
    return tail


def apply_all() -> None:
    files = sorted(_MIGRATIONS.glob("*.sql"))
    if not files:
        raise SystemExit(f"No .sql files found in {_MIGRATIONS}")
    print(f"Target: {_safe_host(settings.supabase_db_url)}")
    print(f"Migrations: {', '.join(f.name for f in files)}\n")

    with _connect() as conn:
        for f in files:
            sql = f.read_text(encoding="utf-8")
            print(f"→ applying {f.name} ({len(sql):,} bytes) …", end=" ", flush=True)
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)  # file's own begin;/commit; bounds the tx
                print("ok")
            except Exception as e:  # noqa: BLE001
                print("FAILED")
                print(f"\n{f.name}: {e}")
                print("\nIf the objects already exist this database was already migrated.")
                raise SystemExit(1)
    print()
    verify()


def verify() -> None:
    import psycopg  # local import
    with psycopg.connect(settings.supabase_db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from information_schema.tables "
                "where table_schema = 'public'"
            )
            n_tables = cur.fetchone()[0]
            cur.execute("select count(*) from public.stages")
            n_stages = cur.fetchone()[0]
            cur.execute(
                "select column_name from information_schema.columns "
                "where table_schema='public' and table_name='properties' "
                "and column_name='agency_id'"
            )
            has_agency = cur.fetchone() is not None
    print(f"public tables : {n_tables}")
    print(f"stages seeded : {n_stages} (expect 9)")
    print(f"agency_id on properties : {'yes' if has_agency else 'NO — run 002_agencies.sql'}")
    ok = n_tables >= _EXPECTED_TABLES and n_stages == 9 and has_agency
    print("\n" + ("✓ schema looks complete." if ok else "⚠ schema incomplete — see above."))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    if "--verify" in sys.argv:
        verify()
    else:
        apply_all()
