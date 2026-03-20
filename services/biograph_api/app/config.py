"""Configuration for biograph_api."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = ""

    @model_validator(mode="after")
    def _validate_critical_settings(self) -> "Settings":
        """Fail fast at startup when critical configuration is missing."""
        missing: list[str] = []
        if not self.database_url:
            missing.append("DATABASE_URL")
        if self.api_token_required and not __import__("os").getenv("API_TOKEN", "").strip():
            missing.append("API_TOKEN (required when API_TOKEN_REQUIRED=true)")
        if missing:
            raise ValueError(
                f"Missing critical configuration — service cannot start: "
                f"{', '.join(missing)}"
            )
        return self
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allow_origins: str = "http://localhost:3000,http://localhost:5173"
    cors_allow_origin_regex: str = (
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
        r"|^https://.*\.railway\.app$"
        r"|^https://.*\.vercel\.app$"
        r"|^https://.*\.alphaengine\.ai$"
        r"|^https://.*\.alpha-engine\.ai$"
    )
    model_artifact_path: str = "../../ml/training/artifacts/baseline_xgb.joblib"
    predict_require_real_model: bool = False
    timeline_analysis_retention_limit: int = 5
    timeline_asr_provider: str = "metadata"
    timeline_ocr_provider: str = "metadata"
    narrative_control_config_json: str = "{}"
    blink_transport_enabled: bool = True
    blink_transport_config_json: str = "{}"
    reward_anticipation_config_json: str = "{}"
    boundary_encoding_config_json: str = "{}"
    au_friction_config_json: str = "{}"
    cta_reception_config_json: str = "{}"
    social_transmission_config_json: str = "{}"
    self_relevance_config_json: str = "{}"
    synthetic_lift_prior_config_json: str = "{}"
    synthetic_lift_prior_calibration_path: str = (
        "../../ml/training/artifacts/synthetic_lift_calibration.json"
    )
    geox_calibration_enabled: bool = False
    product_rollups_enabled: bool = True
    product_rollup_default_tier: str = "creator"
    product_rollup_tier_modes_json: str = "{}"
    neuro_score_taxonomy_enabled: bool = True
    neuro_observability_enabled: bool = True
    neuro_observability_history_path: str = ""
    neuro_observability_history_max_entries: int = 500
    neuro_observability_drift_alert_threshold: float = 12.0
    webcam_capture_archive_enabled: bool = True
    webcam_capture_archive_max_frames: int = 240
    webcam_capture_archive_max_payload_bytes: int = 5_242_880
    webcam_capture_archive_retention_days: int = 30
    webcam_capture_archive_purge_enabled: bool = True
    webcam_capture_archive_purge_batch_size: int = 500
    webcam_capture_archive_encryption_mode: str = "fernet"
    webcam_capture_archive_encryption_key: str = ""
    webcam_capture_archive_encryption_key_id: str = ""
    webcam_capture_archive_observability_window_hours: int = 24
    strict_canonical_trace_fields: bool = False
    synchrony_analysis_enabled: bool = Field(
        default=True, validation_alias="ENABLE_SYNCHRONY_ANALYSIS"
    )

    # Security settings
    api_token_required: bool = True
    rate_limit_rpm: int = 120
    # Supabase Auth — set SUPABASE_JWT_SECRET from Supabase dashboard → Settings → API
    supabase_jwt_secret: str = ""
    supabase_url: str = ""

    @property
    def normalized_database_url(self) -> str:
        """Normalize managed Postgres URLs for SQLAlchemy+psycopg."""

        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def cors_origins(self) -> list[str]:
        """Return cleaned CORS origins."""

        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return singleton settings instance."""

    return Settings()
