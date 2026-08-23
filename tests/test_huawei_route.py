from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.api.routes.auth import require_user
from app.main import app


class FakeHuaweiClient:
    def __init__(self, payload):
        self.payload = payload
        self.post = AsyncMock(
            return_value=httpx.Response(
                200,
                json=payload,
                request=httpx.Request("POST", "https://huawei.example"),
            )
        )


def test_mml_command_preserves_huawei_envelope_and_parses_report():
    client = FakeHuaweiClient(
        {
            "asynchId": "0601_20260823011129_52276",
            "results": [
                {
                    "name": "MBTS-RM13345",
                    "report": "RETCODE = 0\nnot complete",
                    "result": "Operation succeeded.",
                    "retCode": 0,
                    "serialId": -1,
                }
            ],
            "retCode": "90000",
            "retMessage": "Execution succeeded.",
        }
    )
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/command",
                json={"command": "display version;", "ne_names": ["NE-001"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "asynchId": "0601_20260823011129_52276",
        "results": [
            {
                "name": "MBTS-RM13345",
                "report": {"error": "Error: Reporte MML incompleto (No se detectó '---    END')."},
                "result": "Operation succeeded.",
                "retCode": 0,
                "serialId": -1,
            }
        ],
        "retCode": "90000",
        "retMessage": "Execution succeeded.",
    }
    client.post.assert_awaited_once_with(
        "/api/rest/mmlManagement/v1/command",
        headers={"X-Auth-Token": "test-token"},
        json={"command": "display version;", "neNames": ["NE-001"]},
    )


def test_old_public_paths_are_not_registered():
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with TestClient(app) as client:
            assert client.post("/huawei/mml/command").status_code == 404
            assert client.get("/huawei/status").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_mml_command_replaces_report_with_parsed_report():
    report = """+++ NE-001 2026-08-23 10:20:30
RETCODE = 0
---
CELL  STATUS

cell-a  ACTIVE
(Number of results = 1)
---    END"""
    client = FakeHuaweiClient(
        {
            "asynchId": "0601_20260823011129_52276",
            "results": [
                {
                    "name": "MBTS-RM13345",
                    "result": "Operation succeeded.",
                    "retCode": 0,
                    "serialId": -1,
                    "report": report,
                }
            ],
            "retCode": "90000",
            "retMessage": "Execution succeeded.",
        }
    )
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/command",
                json={"command": "display cell;", "ne_names": ["NE-001"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.json() == {
        "asynchId": "0601_20260823011129_52276",
        "results": [
            {
                "name": "MBTS-RM13345",
                "report": {
                    "retCode": 0,
                    "timestamp": "2026-08-23 10:20:30",
                    "records": [{"CELL": "cell-a", "STATUS": "ACTIVE"}],
                },
                "result": "Operation succeeded.",
                "retCode": 0,
                "serialId": -1,
            }
        ],
        "retCode": "90000",
        "retMessage": "Execution succeeded.",
    }
