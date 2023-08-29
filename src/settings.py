from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    forms_api_key: str
    confirmed_participation: bool = False

    model_config = SettingsConfigDict(
        env_prefix="cjrv_", env_file=".env", env_file_encoding="utf-8"
    )
