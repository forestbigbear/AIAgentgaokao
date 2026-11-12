import ipaddress
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

from dotenv import set_key
from pydantic import BaseModel, Field, field_validator

from app.api.responses import AppError
from app.core.config import Settings


FIELDS = {
    "embedding": ("embedding_api_base_url", "embedding_api_key", "embedding_model"),
    "llm": ("llm_api_base_url", "llm_api_key", "llm_model"),
}


class ModelConfigInput(BaseModel):
    base_url: str = Field(max_length=1000)
    model: str = Field(max_length=200)
    api_key: str | None = Field(default=None, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def valid_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("provide an API root URL without credentials, query or fragment")
        if parsed.scheme == "http":
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                loopback = parsed.hostname == "localhost"
            if not loopback:
                raise ValueError("HTTP is allowed only for local model servers")
        elif parsed.scheme != "https":
            raise ValueError("API base URL must use HTTPS or local HTTP")
        if parsed.path.rstrip("/").endswith(("/embeddings", "/chat/completions")):
            raise ValueError("provide the API root URL, not an endpoint URL")
        return value

    @field_validator("model")
    @classmethod
    def valid_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model name is required")
        return value

    @field_validator("api_key")
    @classmethod
    def clean_key(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class ModelConfigStore:
    def __init__(self, env_path: Path):
        self.env_path = env_path
        self._lock = Lock()

    def settings(self) -> Settings:
        return Settings(_env_file=self.env_path)

    @staticmethod
    def public(settings: Settings) -> dict:
        result = {}
        for kind, (base_field, key_field, model_field) in FIELDS.items():
            base_url = getattr(settings, base_field)
            key = getattr(settings, key_field)
            model = getattr(settings, model_field)
            result[kind] = {
                "base_url": base_url, "model": model, "has_key": bool(key),
                "ready": bool(base_url and key and model),
            }
        return result

    def update(self, kind: str, payload: ModelConfigInput | None) -> Settings:
        base_field, key_field, model_field = FIELDS[kind]
        with self._lock:
            current = self.settings()
            key = (payload.api_key if payload else None) or (
                getattr(current, key_field) if payload else ""
            )
            if payload and not key:
                raise AppError(422, "MODEL_KEY_REQUIRED", "API key is required for first-time setup")
            values = {
                base_field.upper(): payload.base_url if payload else "",
                key_field.upper(): key,
                model_field.upper(): payload.model if payload else "",
            }
            self.env_path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(prefix=".env.tmp-", dir=self.env_path.parent)
            os.close(handle)
            try:
                if self.env_path.exists():
                    shutil.copyfile(self.env_path, temporary)
                for name, value in values.items():
                    set_key(temporary, name, value, quote_mode="always", encoding="utf-8")
                os.replace(temporary, self.env_path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return self.settings()
