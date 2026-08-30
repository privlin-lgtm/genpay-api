from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    env: str = "development"
    database_url: str = "sqlite:///./genpay.db"
    secret_key: str = "change-me"
    webhook_signing_secret: str = "change-me"
    internal_api_key: str = "change-me"

    # Revenue split, in basis points (1% = 100 bps) so the default 70/20/10 split
    # is exact integer math with no floating-point representation error. Override
    # via env vars (ARCHIVE_SHARE_BPS etc.) to change the split without a deploy.
    archive_share_bps: int = 7000
    transcriptionist_share_bps: int = 2000
    platform_share_bps: int = 1000


settings = Settings()
