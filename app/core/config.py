from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    use_proxy: bool = False
    proxy_url: str | None = None

    huawei_api_base_url: str
    huawei_username: str
    huawei_password: str
    huawei_ca_cert_path: str | None = None
    # Set to false only for diagnostics (e.g. hitting the API by IP instead of hostname).
    huawei_verify_ssl: bool = True

    request_timeout_seconds: float = 30.0
    # TODO: fixed test token until the real token issuing system is integrated.
    backend_static_token: str = "test-token"


@lru_cache
def get_settings() -> Settings:
    return Settings()
