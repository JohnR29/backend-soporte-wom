import json
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.services.audit import is_enabled, record, redact, upstream_ctx, valid_ip

_EXCLUDED_PATHS = {"/health", "/", "/favicon.ico", "/docs", "/openapi.json"}
_ERROR_BODY_LIMIT = 4096
_ERROR_DETAIL_MAX_CHARS = 2000


def _parse_body(raw: bytes, size: int, max_bytes: int):
    if size == 0:
        return None
    if size > max_bytes:
        return {"_truncated": True, "_size": size}
    try:
        return redact(json.loads(raw))
    except ValueError:
        return {"_non_json": True, "_size": size}


def _error_detail(raw: bytes) -> str | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return raw.decode("utf-8", "replace")[:_ERROR_DETAIL_MAX_CHARS]
    detail = payload.get("detail", payload) if isinstance(payload, dict) else payload
    text = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
    return text[:_ERROR_DETAIL_MAX_CHARS]


class AuditMiddleware:
    """Middleware ASGI puro: no consume el body ni rompe el streaming."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _EXCLUDED_PATHS or not is_enabled():
            await self.app(scope, receive, send)
            return

        max_bytes = get_settings().audit_max_body_bytes
        request_id = uuid.uuid4()
        upstream: dict = {}
        ctx_token = upstream_ctx.set(upstream)

        req_body = bytearray()
        req_size = 0
        status = 500
        resp_size = 0
        error_body = bytearray()
        error_type: str | None = None
        started = time.perf_counter()

        async def receive_wrapper() -> Message:
            nonlocal req_size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                req_size += len(chunk)
                if len(req_body) <= max_bytes:
                    req_body.extend(chunk)
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal status, resp_size
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = str(request_id)
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                resp_size += len(chunk)
                if status >= 400 and len(error_body) < _ERROR_BODY_LIMIT:
                    error_body.extend(chunk)
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except Exception as error:
            error_type = type(error).__name__
            raise
        finally:
            upstream_ctx.reset(ctx_token)
            body = _parse_body(bytes(req_body), req_size, max_bytes)
            headers = Headers(scope=scope)
            client = scope.get("client")
            route = scope.get("route")
            ne_names = None
            command = None
            if isinstance(body, dict):
                command = body.get("command") if isinstance(body.get("command"), str) else None
                names = body.get("ne_names") or ([body["nodeb_name"]] if "nodeb_name" in body else None)
                if isinstance(names, list):
                    ne_names = [str(name) for name in names]

            record(
                {
                    "request_id": request_id,
                    "client_ip": valid_ip(client[0] if client else None),
                    "x_forwarded_for": headers.get("x-forwarded-for"),
                    "method": scope["method"],
                    "path": scope["path"],
                    "route_template": getattr(route, "path", None),
                    "query_params": redact(dict(Request(scope).query_params)) or None,
                    "request_body": body,
                    "request_size": req_size,
                    "status_code": status,
                    "error_type": error_type,
                    "error_detail": _error_detail(bytes(error_body)) if status >= 400 else None,
                    "response_size": resp_size,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "upstream_service": upstream.get("service"),
                    "upstream_status": upstream.get("status"),
                    "upstream_duration_ms": upstream.get("duration_ms"),
                    "upstream_calls": upstream.get("calls"),
                    "ne_names": ne_names,
                    "mml_command": command,
                }
            )
