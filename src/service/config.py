from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDEO_", extra="ignore")
    database_url: str = "postgresql+psycopg://video:video@localhost:5432/video"
    broker_url: str = "redis://localhost:6379/0"
    artifact_root: str = "./artifacts"
    model_name: str = "HuggingFaceTB/SmolVLM2-500M-Video-Instruct"
    max_upload_bytes: int = 500 * 1024 * 1024
    use_fake_inference: bool = True


settings = Settings()
