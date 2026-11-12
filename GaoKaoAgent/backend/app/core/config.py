from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3306, ge=1, le=65535)
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "gaokao_agent"
    db_pool_size: int = Field(default=5, ge=1, le=20)
    log_level: str = "INFO"
    embedding_api_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    llm_api_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    match_rank_weight: int = Field(default=50, ge=0, le=100)
    match_interest_weight: int = Field(default=15, ge=0, le=100)
    match_city_weight: int = Field(default=10, ge=0, le=100)
    match_risk_weight: int = Field(default=10, ge=0, le=100)
    match_data_weight: int = Field(default=15, ge=0, le=100)
    match_reach_ratio: float = Field(default=0.9, gt=0, le=5)
    match_safe_ratio: float = Field(default=1.2, gt=0, le=5)

    @model_validator(mode="after")
    def validate_matching_policy(self):
        total = (self.match_rank_weight + self.match_interest_weight
                 + self.match_city_weight + self.match_risk_weight + self.match_data_weight)
        if total != 100:
            raise ValueError("matching weights must sum to 100")
        if self.match_reach_ratio >= self.match_safe_ratio:
            raise ValueError("MATCH_REACH_RATIO must be lower than MATCH_SAFE_RATIO")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

