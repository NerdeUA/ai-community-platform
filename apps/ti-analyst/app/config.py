from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://ti_analyst:ti_analyst@postgres:5432/ti_analyst"
    litellm_base_url: str = "http://litellm:4000"
    litellm_api_key: str
    triage_model: str = "cheap"
    analyst_model: str = "cheap"
    infra_model: str = "cheap"
    platform_core_url: str = "http://core"
    app_internal_token: str
    opensearch_url: str = "http://opensearch:9200"
    openclaw_url: str = "http://openclaw:8000"
    telegram_bot_token: str = ""
    telegram_alert_chat_id: str = ""
    telegram_bot_allowed_ids: str = ""  # comma-separated user IDs, fallback if DB not set
    telegram_api_id: int | None = None
    telegram_api_hash: str = ""
    admin_public_url: str = "http://localhost:8088/admin/sources"
    enable_test_endpoints: bool = False
    ingestion_cron: str = "0 */1 * * *"
    openclaw_enabled: bool = False

    model_config = {"env_file": ".env"}


settings = Settings()
