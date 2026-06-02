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
    agent_bootstrap_email: str = "admin@palacegate.co.uk"
    agent_bootstrap_password: str = "ChangeMeImmediately!"

    # --- Airtable -----------------------------------------------------------
    airtable_token: str = ""
    airtable_base_id: str = "appgqHgbJut9LYksm"

    airtable_table_properties: str = "tblbzHoCEe06wxe24"
    airtable_table_landlords: str = "tblVIXNIkrRp9Xxh2"
    airtable_table_tenants: str = "tblTenantTableId"
    airtable_table_diary: str = "tblE9U8jtmI3DTHbJ"
    airtable_table_financials: str = "tblj71Zu2Jn260nY0"
    airtable_table_checklist: str = "tblGiQey64sUuIp2j"
    airtable_table_submissions: str = "tblaflLP7VFCoPMJo"
    airtable_table_stages: str = "tblIHHIgbF7WbL4bt"
    airtable_table_gate_log: str = "tbljoHc7WkcRalZPS"
    airtable_table_compliance: str = "tblComplianceId"
    airtable_table_offers: str = "tblJLapFX84NYqAPw"  # created 2026-05-25 (offer lifecycle)
    airtable_table_sent_documents: str = "tblyG0gijqAN5bo5x"  # created 2026-06-01 (per-stage sent docs)

    # --- SMTP ---------------------------------------------------------------
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_use_tls: bool = True
    from_email: str = "noreply@palacegate.co.uk"
    admin_email: str = "admin@palacegate.co.uk"
    lesley_email: str = "lesley@palacegate.co.uk"

    # --- DocuSeal -----------------------------------------------------------
    # Kept for when we flip back to DocuSeal; the live signing pipeline is on
    # DocuSign (app/core/signing.py picks the provider based on app_env).
    docuseal_url: str = "https://docuseal.palacegate.co.uk"
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
    brand_navy: str = "#004AAD"
    brand_gold: str = "#C9A24C"
    brand_name: str = "Palace Gate Lettings"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
