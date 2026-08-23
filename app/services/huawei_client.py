from pathlib import Path
from dataclasses import dataclass
import time

import httpx

from app.core.config import get_settings


def _build_client() -> httpx.AsyncClient:
    """Single place where proxy and CA cert handling for the Huawei API live."""
    settings = get_settings()

    client_kwargs: dict = {
        "base_url": settings.huawei_api_base_url,
        "timeout": settings.request_timeout_seconds,
    }

    # Proxy is only needed on the Ubuntu VM; local dev leaves USE_PROXY=false.
    if settings.use_proxy:
        if not settings.proxy_url:
            raise RuntimeError("USE_PROXY is true but PROXY_URL is not set")
        client_kwargs["proxy"] = settings.proxy_url

    if settings.huawei_ca_cert_path:
        cert_path = Path(settings.huawei_ca_cert_path)
        if not cert_path.is_file():
            raise RuntimeError(f"HUAWEI_CA_CERT_PATH does not exist: {cert_path}")
        client_kwargs["verify"] = str(cert_path)

    return httpx.AsyncClient(**client_kwargs)


_client: httpx.AsyncClient | None = None


@dataclass
class _HuaweiSession:
    access_session: str
    roa_rand: str
    expires_at: float


_huawei_session: _HuaweiSession | None = None


def get_client() -> httpx.AsyncClient:
    """Lazily-built shared client so config errors surface on first use, not import."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


async def get_huawei_headers() -> dict[str, str]:
    """Return headers for the shared Huawei account, logging in when needed."""
    global _huawei_session
    settings = get_settings()

    if _huawei_session is None or time.monotonic() >= _huawei_session.expires_at:
        response = await get_client().put(
            "/api/rest/securityManagement/v1/oauth/token",
            json={
                "grantType": "password",
                "userName": settings.huawei_username,
                "value": settings.huawei_password,
            },
        )
        response.raise_for_status()
        payload = response.json()
        try:
            access_session = payload["accessSession"]
            roa_rand = payload["roaRand"]
            expires = int(payload["expires"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Huawei login returned an invalid response") from error

        _huawei_session = _HuaweiSession(
            access_session=access_session,
            roa_rand=roa_rand,
            expires_at=time.monotonic() + max(expires - 30, 1),
        )

    return {
        "X-Auth-Token": _huawei_session.access_session,
        "X-ROA-Rand": _huawei_session.roa_rand,
    }


async def close_client() -> None:
    global _client, _huawei_session
    _huawei_session = None
    if _client is not None:
        await _client.aclose()
        _client = None
