from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.api.routes.alarms import _HERMES_FILTER, _epoch_ms_to_iso
from app.api.routes.auth import require_user
from app.main import app


class FakeHuaweiClient:
    def __init__(self, payload, status_code=200):
        self.get = AsyncMock(
            return_value=httpx.Response(
                status_code,
                json=payload,
                request=httpx.Request("GET", "https://huawei.example"),
            )
        )


def _call_hermes_endpoint(client):
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.alarms.get_client", return_value=client),
            patch(
                "app.api.routes.alarms.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            TestClient(app) as test_client,
        ):
            return test_client.get("/alarms/hermes")
    finally:
        app.dependency_overrides.clear()


def test_hermes_alarms_maps_fields_and_renames_columns():
    client = FakeHuaweiClient(
        {
            "alarmInformationList": [
                {
                    "alarmId": "13882",
                    "alarmName": "NR Cell Unavailable",
                    "comments": "Enlace caído",
                    "nativeMoName": "NodeB-001",
                    "alarmRaisedTime": "1735689600000",
                    "alarmClearedTime": "0",
                    "csn": "998877",
                }
            ],
            "marker": "null",
            "retCode": "0",
        }
    )

    response = _call_hermes_endpoint(client)

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["alarms"][0] == {
        "Alarm ID": "13882",
        "Alarm name": "NR Cell Unavailable",
        "Comment": "Enlace caído",
        "MO Name": "NodeB-001",
        "Occurred On (NT)": _epoch_ms_to_iso("1735689600000"),
        "Cleared On (NT)": None,
        "Log Serial Number": "998877",
    }


def test_hermes_alarms_sends_expected_query_params():
    client = FakeHuaweiClient({"alarmInformationList": [], "marker": "null"})

    response = _call_hermes_endpoint(client)

    assert response.status_code == 200
    client.get.assert_awaited_once_with(
        "/api/rest/faultSupervisonManagement/v1/alarms",
        headers={"X-Auth-Token": "test-token"},
        params={
            "dataType": "CURRENT",
            "alarmAckState": "ALL_ACTIVE_ALARMS",
            "filter": _HERMES_FILTER,
            "limit": 500,
        },
    )


def test_hermes_alarms_translates_huawei_error_envelope():
    client = FakeHuaweiClient(
        {"retCode": "90018", "retMessage": "Invalid filter parameter."},
        status_code=400,
    )

    response = _call_hermes_endpoint(client)

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid filter parameter."
