from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    forms_api_key: str
    responses_api_url: str
    confirmed_api_url: str
    only_show_confirmed: bool = False

    model_config = SettingsConfigDict(
        env_prefix="cjrv_", env_file=".env", env_file_encoding="utf-8"
    )


settings = Settings()  # type: ignore
