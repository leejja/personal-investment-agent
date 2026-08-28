from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = ""
    kiwoom_app_key: str = ""
    kiwoom_secret_key: str = ""
    ecos_api_key: str = ""
    opendart_api_key: str = ""
    kis_app_key: str = ""
    kis_secret_key: str = ""
    kis_env: str = ""

    model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            )


settings = Settings()
