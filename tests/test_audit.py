from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.audit import redact, valid_ip


def test_redact_masks_sensitive_keys_recursively():
    data = {"password": "x", "nested": {"Token": "y", "ok": 1}, "items": [{"hash": "z"}]}
    assert redact(data) == {"password": "***", "nested": {"Token": "***", "ok": 1}, "items": [{"hash": "***"}]}


def test_valid_ip_rejects_non_ip_hosts():
    assert valid_ip("testclient") is None
    assert valid_ip("10.0.0.1") == "10.0.0.1"


def test_middleware_records_failed_auth_request():
    records = []
    with (
        patch("app.api.audit_middleware.is_enabled", return_value=True),
        patch("app.api.audit_middleware.record", side_effect=records.append),
        TestClient(app) as client,
    ):
        response = client.get("/alarms/hermes")

    assert response.status_code == 401
    assert "x-request-id" in response.headers
    entry = records[0]
    assert entry["status_code"] == 401
    assert entry["path"] == "/alarms/hermes"
    assert entry["error_detail"] == "Bearer token required"
    assert entry["client_ip"] is None


def test_middleware_skips_noise_paths():
    records = []
    with (
        patch("app.api.audit_middleware.is_enabled", return_value=True),
        patch("app.api.audit_middleware.record", side_effect=records.append),
        TestClient(app) as client,
    ):
        for path in ("/health", "/", "/favicon.ico", "/docs", "/openapi.json"):
            client.get(path)

    assert records == []
