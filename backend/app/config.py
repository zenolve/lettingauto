"""Centralised configuration loaded from environment variables.

All settings live in one place; no module reads from `os.environ` directly.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ----------------------------------------------------------------
    app_env: str = "development"
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    # --- Auth ---------------------------------------------------------------
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_ttl_hours: int = 12
    # Supabase Auth: agents sign in on the frontend via supabase-js (email /
    # Google / Microsoft); the backend verifies the Supabase access token with
    # the project's JWT secret (Supabase → Settings → API → JWT Secret).
    supabase_jwt_secret: str = ""
    # Legacy single-user login. Handy for local dev and the smoke script; it
    # auto-provisions a "Bootstrap Agency". Disable in production.
    allow_bootstrap_login: bool = True
    agent_bootstrap_email: str = "admin@example.com"
    agent_bootstrap_password: str = "ChangeMeImmediately!"

    # --- Supabase (Postgres) --------------------------------------------------
    # The backend talks straight to Supabase's Postgres. Use the connection
    # string from Supabase → Settings → Database → Connection string. The
    # session pooler URI (port 5432) is recommended; any plain Postgres works
    # too (e.g. the docker-compose.dev.yml `db` service).
    supabase_db_url: str = ""
    supabase_pool_max_size: int = 5
    # Optional — only needed if you later use Supabase Storage / client APIs.
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # --- Stripe ----------------------------------------------------------------
    # Payments (holding deposits / deposits / rent) via Stripe Checkout, plus
    # agency billing. Leave the secret key blank to disable billing entirely
    # (endpoints return 501 and the tenancy-fee gate is skipped).
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_currency: str = "gbp"
    # Agency pricing: £50 one-time per new tenancy + £5/month per live tenancy.
    # stripe_price_live_tenancy is a recurring per-unit Price id (£5/month);
    # the subscription quantity tracks the agency's live tenancy count.
    stripe_price_live_tenancy: str = ""
    stripe_tenancy_setup_fee_pence: int = 5000

    # --- SMTP ---------------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_use_tls: bool = True
    from_email: str = "noreply@lettingauto.app"
    admin_email: str = "admin@lettingauto.app"
    # Back-office assignee for NRL tax-cert diary entries (name is historical).
    lesley_email: str = "admin@lettingauto.app"

    # --- DocuSeal -----------------------------------------------------------
    # Kept for when we flip back to DocuSeal; the live signing pipeline is on
    # DocuSign (app/core/signing.py picks the provider based on app_env).
    docuseal_url: str = "https://docuseal.example.com"
    docuseal_token: str = ""
    docuseal_webhook_secret: str = ""

    docuseal_template_offer_letter: int = 22
    docuseal_template_instruction_letter: int = 15
    docuseal_template_intro_valuation: int = 16
    docuseal_template_terms_of_business: int = 20
    docuseal_template_palace_gate_doc: int = 18

    # --- DocuSign -----------------------------------------------------------
    # Used when app_env in {"dev","production"} — see app/core/signing.py.
    # JWT bearer flow needs the integration key + impersonation user + a
    # private RSA key (the matching public key lives in DocuSign admin).
    docusign_integration_key: str = ""
    docusign_user_id: str = ""
    docusign_account_id: str = ""
    docusign_private_key_path: str = ""              # filesystem path to RSA private key
    docusign_auth_server: str = "account-d.docusign.com"   # sandbox; prod = "account.docusign.com"
    docusign_base_path: str = "https://demo.docusign.net/restapi"
    docusign_connect_hmac_secret: str = ""           # for verifying Connect POSTs

    # --- Paragon (referencing) ----------------------------------------------
    paragon_url: str = "https://api.paragonadvance.com"
    paragon_token: str = ""

    # --- Scheduler ----------------------------------------------------------
    scheduler_internal_token: str = "dev-only-scheduler-token"

    # --- Brand --------------------------------------------------------------
    # Platform defaults. At runtime, documents/emails are branded with the
    # CURRENT AGENCY's name/colours (see app/core/branding.py); these values
    # are the fallback when no agency scope is set.
    brand_navy: str = "#004AAD"
    brand_gold: str = "#C9A24C"
    brand_name: str = "LettingAuto"
    platform_name: str = "LettingAuto"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
