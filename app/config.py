from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    kiwoom_app_key: str = ""
    kiwoom_secret_key: str = ""
    ecos_api_key: str = ""
    opendart_api_key: str = ""

    model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            )


settings = Settings()
