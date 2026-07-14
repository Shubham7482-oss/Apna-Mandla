"""
app/core/config.py — centralised settings.
"""

import os
import warnings
from typing import List, Optional, Union

from pydantic import computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_KEYS = frozenset({
    "CHANGE_ME_IN_PRODUCTION_GENERATE_WITH_openssl_rand_hex_32",
    "a_very_secret_key", "secret", "your_secret_key", "changeme", "password",
})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        case_sensitive=True, extra="ignore",
    )

    # ── Project ───────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Apna Mandla API"
    API_V1_STR:   str = "/api/v1"
    DEBUG:        bool = False

    # ── JWT ───────────────────────────────────────────────────────────────────
    SECRET_KEY:                    str = "CHANGE_ME_IN_PRODUCTION_GENERATE_WITH_openssl_rand_hex_32"
    ADMIN_SECRET_KEY:              Optional[str] = None
    ALGORITHM:                     str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:   int = 15
    REFRESH_TOKEN_EXPIRE_DAYS:     int = 7
    ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 24
    OTP_EXPIRY_SECONDS:            int = 300

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./apna_mandla.db"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_HOST:     str = "localhost"
    REDIS_PORT:     int = 6379
    REDIS_DB:       int = 0
    REDIS_PASSWORD: Optional[str] = None

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = []

    # ── Cookies ───────────────────────────────────────────────────────────────
    COOKIE_SECURE:           bool = False
    COOKIE_SAMESITE:         str  = "strict"
    COOKIE_DOMAIN:           Optional[str] = None
    COOKIE_HTTPONLY_REFRESH: bool = True

    # ── Firebase ──────────────────────────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = "firebase-credentials.json"
    FIREBASE_CREDENTIALS_JSON: Optional[str] = None
    FCM_SERVER_KEY:            Optional[str] = None

    # ── Fraud & Transaction Limits ────────────────────────────────────────────
    # Per-transaction ceiling (INR)
    FRAUD_MAX_SINGLE_TXN_AMOUNT:   float = 50_000.0
    # Maximum total debits from one wallet in a calendar day (INR)
    FRAUD_MAX_DAILY_DEBIT_AMOUNT:  float = 100_000.0
    # Maximum number of debit transactions per wallet per hour
    FRAUD_MAX_HOURLY_TXN_COUNT:    int   = 20
    # Minimum seconds between two transactions from the same wallet
    FRAUD_MIN_TXN_INTERVAL_SECS:   int   = 5
    # A single txn ≥ this % of the wallet's 30-day average triggers a flag
    FRAUD_VELOCITY_SPIKE_FACTOR:   float = 10.0
    # Minimum withdrawal amount (INR)
    MIN_WITHDRAWAL_AMOUNT:         float = 10.0

    # ── Udhar (Credit System) ─────────────────────────────────────────────────
    # Maximum credit limit a shop can grant (INR)
    UDHAR_MAX_CREDIT_LIMIT:        float = 50_000.0
    # Maximum annual interest rate allowed (%)
    UDHAR_MAX_INTEREST_RATE_PCT:   float = 36.0
    # How often the interest scheduler runs (hours)
    UDHAR_INTEREST_APPLY_INTERVAL_HOURS: int = 24

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        is_debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        if v in _INSECURE_KEYS:
            if not is_debug:
                raise ValueError("SECRET_KEY is insecure. Generate: openssl rand -hex 32")
            warnings.warn("[SECURITY] SECRET_KEY is insecure. Dev only.", stacklevel=2)
        if len(v) < 32:
            raise ValueError(f"SECRET_KEY too short ({len(v)} chars, min 32).")
        return v

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES", mode="after")
    @classmethod
    def validate_access_expiry(cls, v: int) -> int:
        is_debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        if v > 60 and not is_debug:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be ≤60 in production.")
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [o.strip() for o in v.split(",") if o.strip()]
        return [str(o) for o in v] if isinstance(v, list) else []

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def reject_wildcard_in_production(cls, v: List[str]) -> List[str]:
        is_debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        if "*" in v and not is_debug:
            raise ValueError("CORS_ORIGINS='*' is not allowed in production.")
        if "*" in v:
            warnings.warn("[SECURITY] CORS_ORIGINS='*'. Dev only.", stacklevel=2)
        return v

    @model_validator(mode="after")
    def configure_admin_key(self) -> "Settings":
        if not self.ADMIN_SECRET_KEY:
            is_debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
            if not is_debug:
                warnings.warn("[SECURITY] ADMIN_SECRET_KEY not set. Using SECRET_KEY.", stacklevel=2)
            object.__setattr__(self, "ADMIN_SECRET_KEY", self.SECRET_KEY)
        return self

    # ── Computed ──────────────────────────────────────────────────────────────

    @computed_field  # type: ignore[misc]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        return self.DATABASE_URL

    @computed_field  # type: ignore[misc]
    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


settings = Settings()
