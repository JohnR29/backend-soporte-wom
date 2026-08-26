from pathlib import Path
from dataclasses import dataclass
import asyncio
import logging
import time

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _build_client() -> httpx.AsyncClient:
    """Single place where proxy and CA cert handling for the Huawei API live."""
    settings = get_settings()

    client_kwargs: dict = {
        "base_url": settings.huawei_api_base_url,
        "timeout": settings.request_timeout_seconds,
        # Never let httpx auto-pick up HTTP(S)_PROXY from the OS environment;
        # proxy usage must only come from USE_PROXY/PROXY_URL in .env.
        "trust_env": False,
    }

    # Proxy is only needed on the Ubuntu VM; local dev leaves USE_PROXY=false.
    if settings.use_proxy:
        if not settings.proxy_url:
            raise RuntimeError("USE_PROXY is true but PROXY_URL is not set")
        client_kwargs["proxy"] = settings.proxy_url

    if not settings.huawei_verify_ssl:
        client_kwargs["verify"] = False
    elif settings.huawei_ca_cert_path:
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
_session_lock = asyncio.Lock()
_last_activity: float | None = None
_HANDSHAKE_AFTER_SECONDS = 29 * 60
_KEEPALIVE_CHECK_SECONDS = 60


def get_client() -> httpx.AsyncClient:
    """Lazily-built shared client so config errors surface on first use, not import."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


async def get_huawei_headers() -> dict[str, str]:
    """Return headers for the shared Huawei account, logging in when needed."""
    global _huawei_session, _last_activity
    settings = get_settings()

    async with _session_lock:
        if _huawei_session is None or time.monotonic() >= _huawei_session.expires_at:
            response = await get_client().put(
                "/api/rest/securityManagement/v1/oauth/token",
                json={
                    "grantType": "password",
                    "userName": settings.huawei_username,
                    "value": settings.huawei_password,
                },
            )
            if response.is_error:
                logger.error("Huawei login failed: HTTP %s, body=%s", response.status_code, response.text)
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
            _last_activity = time.monotonic()

    return {
        "X-Auth-Token": _huawei_session.access_session,
        "X-ROA-Rand": _huawei_session.roa_rand,
    }


def mark_huawei_activity() -> None:
    global _last_activity
    _last_activity = time.monotonic()


async def keep_huawei_session_alive() -> None:
    """Renew an active Huawei session after 29 minutes without API activity."""
    global _huawei_session, _last_activity
    async with _session_lock:
        if _huawei_session is None or _last_activity is None:
            return
        if time.monotonic() - _last_activity < _HANDSHAKE_AFTER_SECONDS:
            return

        try:
            response = await get_client().post(
                "/api/rest/securityManagement/v1/oauth/handshake",
                headers={"X-Auth-Token": _huawei_session.access_session},
                json={},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 401:
                _huawei_session = None
                _last_activity = None
            logger.warning("Huawei handshake failed: HTTP %s", error.response.status_code)
        except httpx.HTTPError:
            logger.warning("Huawei handshake could not be completed", exc_info=True)
        else:
            _last_activity = time.monotonic()
            logger.info("Huawei session renewed by handshake")


async def huawei_keepalive_loop() -> None:
    while True:
        await asyncio.sleep(_KEEPALIVE_CHECK_SECONDS)
        await keep_huawei_session_alive()


async def close_client() -> None:
    global _client, _huawei_session, _last_activity
    _huawei_session = None
    _last_activity = None
    if _client is not None:
        await _client.aclose()
        _client = None
