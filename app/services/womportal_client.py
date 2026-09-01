import httpx

from app.core.config import get_settings

_client: httpx.AsyncClient | None = None


def _build_client() -> httpx.AsyncClient:
    settings = get_settings()

    client_kwargs: dict = {
        "base_url": settings.womportal_api_base_url,
        "timeout": settings.request_timeout_seconds,
        # Never let httpx auto-pick up HTTP(S)_PROXY from the OS environment;
        # proxy usage must only come from USE_PROXY/PROXY_URL in .env.
        "trust_env": False,
    }

    if settings.use_proxy:
        if not settings.proxy_url:
            raise RuntimeError("USE_PROXY is true but PROXY_URL is not set")
        client_kwargs["proxy"] = settings.proxy_url

    return httpx.AsyncClient(**client_kwargs)


def get_client() -> httpx.AsyncClient:
    """Lazily-built shared client so config errors surface on first use, not import."""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


async def get_tickets_abiertos(sitio: str) -> dict:
    """Query open tickets for a site from the WOM Portal API."""
    settings = get_settings()
    response = await get_client().post(
        "/api/tickets/tickets_abiertos",
        json={
            "hash": settings.womportal_hash,
            "id_sistema": settings.womportal_id_sistema,
            "sitio": sitio,
        },
    )
    response.raise_for_status()
    return response.json()


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
