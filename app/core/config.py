from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Application
    app_name: str = "MyDenning"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me-in-production"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+asyncpg://mydenning:mydenning@localhost:5432/mydenning"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_index_prefix: str = "mydenning"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # S3 Storage
    s3_endpoint_url: Optional[str] = None
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_name: str = "mydenning-documents"
    s3_region: str = "us-east-1"

    # Anthropic API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    # JWT Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # OCR
    tesseract_cmd: str = "/usr/bin/tesseract"

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200

    # Retrieval
    retrieval_top_k: int = 20
    rerank_top_k: int = 10

    # External Legal Source API Keys (optional — adapters degrade gracefully without them)
    courtlistener_api_token: str = ""  # Free: register at courtlistener.com
    laws_africa_api_token: str = ""  # Free: register at edit.laws.africa
    canlii_api_key: str = ""  # Free: register at developer.canlii.org
    indian_kanoon_api_key: str = ""  # Apply at indiankanoon.org/api

    # Email intake (inbound email parsing — SendGrid, Mailgun, or Postmark)
    email_intake_enabled: bool = False
    email_intake_provider: str = "sendgrid"  # sendgrid, mailgun, postmark
    email_intake_webhook_secret: str = ""  # verify inbound webhook authenticity
    email_intake_domain: str = ""  # e.g. "ingest.mydenning.com"

    # Outbound email (for notifications, digests, client comms)
    email_provider: str = "smtp"  # smtp, sendgrid, postmark
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    sendgrid_api_key: str = ""  # if email_provider=sendgrid
    postmark_server_token: str = ""  # if email_provider=postmark
    email_from_address: str = "noreply@mydenning.com"
    email_from_name: str = "MyDenning"

    # Payments (Stripe or Paystack)
    payment_provider: str = ""  # stripe, paystack, or empty to disable
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    paystack_secret_key: str = ""
    paystack_webhook_secret: str = ""

    # Google Calendar
    google_client_id: str = ""
    google_client_secret: str = ""

    # Cloud Storage (Google Drive / OneDrive)
    gdrive_client_id: str = ""
    gdrive_client_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
