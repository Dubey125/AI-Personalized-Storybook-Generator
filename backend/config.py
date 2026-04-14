import os
from pathlib import Path


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Settings:
    def __init__(self) -> None:
        project_root = Path(__file__).resolve().parent.parent
        self.api_title = os.getenv("API_TITLE", "Personalized AI Storybook Generator")
        self.allowed_origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
        self.max_upload_size_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB", "8"))
        self.max_upload_size_bytes = self.max_upload_size_mb * 1024 * 1024
        self.allowed_extensions = {"jpg", "jpeg", "png", "webp"}
        self.outputs_mount_path = "/outputs"
        self.api_auth_token = os.getenv("API_AUTH_TOKEN", "").strip()
        self.max_upload_image_pixels = int(os.getenv("MAX_UPLOAD_IMAGE_PIXELS", "25000000"))
        self.max_name_length = int(os.getenv("MAX_NAME_LENGTH", "40"))
        self.rate_limit_window_seconds = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
        self.rate_limit_max_requests = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "120"))
        self.enable_redis_queue = _as_bool(os.getenv("ENABLE_REDIS_QUEUE", "false"))
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
        self.redis_queue_name = os.getenv("REDIS_QUEUE_NAME", "storybook-jobs").strip()
        self.redis_job_timeout_seconds = int(os.getenv("REDIS_JOB_TIMEOUT_SECONDS", "3600"))
        self.character_training_mode = os.getenv("CHARACTER_TRAINING_MODE", "embedding_seed").strip().lower()
        self.character_training_command = os.getenv("CHARACTER_TRAINING_COMMAND", "").strip()
        self.character_training_timeout_seconds = int(os.getenv("CHARACTER_TRAINING_TIMEOUT_SECONDS", "7200"))
        self.default_lora_adapter_path = os.getenv(
            "DEFAULT_LORA_ADAPTER_PATH",
            str(project_root / "backend" / "models" / "child_model.safetensors"),
        ).strip()
        self.default_lora_adapter_scale = _as_float(os.getenv("DEFAULT_LORA_ADAPTER_SCALE", "0.85"), 0.85)
        self.sqlite_db_path = os.getenv("SQLITE_DB_PATH", "outputs/storybook.db").strip()
        self.retention_hours = int(os.getenv("RETENTION_HOURS", "168"))
        self.retention_enabled = _as_bool(os.getenv("RETENTION_ENABLED", "true"))
        self.metrics_enabled = _as_bool(os.getenv("METRICS_ENABLED", "true"))


settings = Settings()
