import asyncio
import ipaddress
import logging
import time
from contextvars import ContextVar

from app.core.config import get_settings
from app.db import session as db
from app.db.models import ApiAuditLog

logger = logging.getLogger(__name__)

_QUEUE_MAXSIZE = 10_000
_FLUSH_TIMEOUT_SECONDS = 5
_SENSITIVE_KEYS = {"password", "passwd", "token", "authorization", "hash", "secret"}

_queue: asyncio.Queue[dict] | None = None
_writer_task: asyncio.Task | None = None

# Acumulador por request, llenado por los hooks de httpx de los clientes upstream.
upstream_ctx: ContextVar[dict | None] = ContextVar("audit_upstream", default=None)


def is_enabled() -> bool:
    return _queue is not None


async def init_audit() -> None:
    global _queue, _writer_task
    url = get_settings().database_url
    if not url:
        logger.info("Audit disabled: DATABASE_URL is not set")
        return
    db.init_db(url)
    _queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _writer_task = asyncio.create_task(_writer())


async def close_audit() -> None:
    global _queue, _writer_task
    if _queue is None:
        return
    try:
        await asyncio.wait_for(_queue.join(), _FLUSH_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.warning("Audit queue not fully flushed on shutdown")
    if _writer_task is not None:
        _writer_task.cancel()
        try:
            await _writer_task
        except asyncio.CancelledError:
            pass
    _queue = None
    _writer_task = None
    await db.close_db()


def record(entry: dict) -> None:
    if _queue is None:
        return
    try:
        _queue.put_nowait(entry)
    except asyncio.QueueFull:
        logger.warning("Audit queue full, dropping record for %s", entry.get("path"))


async def _writer() -> None:
    assert _queue is not None
    while True:
        entry = await _queue.get()
        try:
            async with db.get_sessionmaker()() as session:
                session.add(ApiAuditLog(**entry))
                await session.commit()
        except Exception:
            logger.warning("Failed to write audit record", exc_info=True)
        finally:
            _queue.task_done()


def redact(value):
    if isinstance(value, dict):
        return {
            key: "***" if str(key).lower() in _SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def valid_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def upstream_hooks(service: str) -> dict:
    """Event hooks de httpx que acumulan estado y duración de las llamadas upstream."""

    async def on_request(request) -> None:
        request.extensions["audit_t0"] = time.perf_counter()

    async def on_response(response) -> None:
        ctx = upstream_ctx.get()
        started = response.request.extensions.get("audit_t0")
        if ctx is None or started is None:
            return
        ctx.setdefault("service", service)
        ctx["status"] = response.status_code
        ctx["duration_ms"] = ctx.get("duration_ms", 0) + int((time.perf_counter() - started) * 1000)
        ctx["calls"] = ctx.get("calls", 0) + 1

    return {"request": [on_request], "response": [on_response]}
