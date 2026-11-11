from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routes.alarms import _HERMES_FILTER, _LICENSE_TRIAL_FILTER, _epoch_ms_to_iso
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
    return _call_alarms_endpoint("/alarms/hermes", client)


def _call_license_trial_endpoint(client, params=None):
    return _call_alarms_endpoint("/alarms/license-trial", client, params)


def _call_alarms_endpoint(path, client, params=None):
    app.dependency_overrides[require_user] = lambda: "operator-1"
    site_name = path.rsplit("/", 1)[-1]
    try:
        with (
            patch(
                "app.api.routes.alarms.resolve_alarm_name",
                new=AsyncMock(
                    return_value={
                        "input": site_name,
                        "resolved": site_name,
                        "resolved_site": site_name,
                        "status": "resolved",
                    }
                ),
            ),
            patch("app.api.routes.alarms.get_client", return_value=client),
            patch(
                "app.api.routes.alarms.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            TestClient(app) as test_client,
        ):
            return test_client.get(path, params=params)
    finally:
        app.dependency_overrides.clear()


def _call_site_alarms_with_resolution(client, resolution, params=None, resolver_error=None):
    app.dependency_overrides[require_user] = lambda: "operator-1"
    resolver = AsyncMock(return_value=resolution)
    if resolver_error is not None:
        resolver.side_effect = resolver_error
    try:
        with (
            patch("app.api.routes.alarms.resolve_alarm_name", new=resolver),
            patch("app.api.routes.alarms.get_client", return_value=client),
            patch(
                "app.api.routes.alarms.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.get("/alarms/an0069", params=params)
    finally:
        app.dependency_overrides.clear()
    return response, resolver


@pytest.mark.parametrize(
    ("params", "target_column", "resolved_node", "technology"),
    [
        (None, "nodo", "MBTS-AN0069", "4G"),
        ({"technology": "3G"}, "nodeb", "UAN0069", "3G"),
    ],
)
def test_site_alarms_resolve_canonical_node_before_huawei_call(
    params, target_column, resolved_node, technology
):
    client = FakeHuaweiClient({"alarmInformationList": [], "marker": "null"})
    resolution = {
        "input": "an0069",
        "resolved": resolved_node,
        "resolved_site": "AN0069",
        "status": "resolved",
    }

    response, resolver = _call_site_alarms_with_resolution(client, resolution, params)

    assert response.status_code == 200
    assert response.json()["user_input"] == "an0069"
    assert response.json()["resolved_site"] == "AN0069"
    assert response.json()["resolved_node"] == resolved_node
    assert response.json()["technology"] == technology
    resolver.assert_awaited_once_with("an0069", technology)
    assert client.get.await_args.kwargs["params"]["baseObjectInstance"] == resolved_node


def test_site_alarms_returns_not_found_suggestions_without_calling_huawei():
    client = FakeHuaweiClient({"alarmInformationList": []})
    suggestions = [
        {
            "nemonica": "AN0069",
            "nodo": "MBTS-AN0069",
            "nodeb": "UAN0069",
            "similarity": 0.8,
        }
    ]
    resolution = {
        "input": "an0069",
        "resolved": None,
        "resolved_site": None,
        "status": "not_found",
        "suggestions": suggestions,
    }

    response, _ = _call_site_alarms_with_resolution(client, resolution)

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
    assert response.json()["user_input"] == "an0069"
    assert response.json()["suggestions"] == suggestions
    client.get.assert_not_awaited()


def test_site_alarms_returns_missing_mapping_metadata_without_calling_huawei():
    client = FakeHuaweiClient({"alarmInformationList": []})
    resolution = {
        "input": "an0069",
        "resolved": None,
        "resolved_site": "AN0069",
        "status": "missing_mapping",
        "available_technologies": ["4G", "5G"],
    }

    response, _ = _call_site_alarms_with_resolution(
        client, resolution, {"technology": "3G"}
    )

    assert response.status_code == 404
    assert response.json()["error"] == "missing_mapping"
    assert response.json()["resolved_site"] == "AN0069"
    assert response.json()["technology"] == "3G"
    assert response.json()["available_technologies"] == ["4G", "5G"]
    client.get.assert_not_awaited()


def test_site_alarms_returns_503_without_calling_huawei_when_directory_is_unavailable():
    client = FakeHuaweiClient({"alarmInformationList": []})

    response, _ = _call_site_alarms_with_resolution(
        client,
        None,
        resolver_error=HTTPException(status_code=503, detail="directory unavailable"),
    )

    assert response.status_code == 503
    assert response.json()["error"] == "service_unavailable"
    assert response.json()["details"] == "site_directory_unreachable"
    client.get.assert_not_awaited()


def test_site_alarms_rejects_unsupported_technology_before_resolution():
    client = FakeHuaweiClient({"alarmInformationList": []})
    resolution = {"input": "an0069", "resolved": "MBTS-AN0069", "status": "resolved"}

    response, resolver = _call_site_alarms_with_resolution(
        client, resolution, {"technology": "2G"}
    )

    assert response.status_code == 422
    resolver.assert_not_awaited()
    client.get.assert_not_awaited()


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


def test_license_trial_alarms_maps_fields_and_renames_columns():
    client = FakeHuaweiClient(
        {
            "alarmInformationList": [
                {
                    "alarmId": "26817",
                    "alarmName": "License Trial Expiration",
                    "comments": "Licencia por expirar",
                    "nativeMoName": "NodeB-001",
                    "objectInstance": "Function Type=eNodeB Function, Trial Reason=Expired License, Grace Period Expire Date=2026-10-10",
                    "alarmRaisedTime": "1735689600000",
                    "alarmClearedTime": "0",
                    "csn": "998877",
                }
            ],
            "marker": "next-page",
        }
    )

    response = _call_license_trial_endpoint(client)

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["marker"] == "next-page"
    assert body["alarms"][0] == {
        "Alarm ID": "26817",
        "Alarm name": "License Trial Expiration",
        "Comment": "Licencia por expirar",
        "MO Name": "NodeB-001",
        "Function Type": "eNodeB Function",
        "Trial Reason": "Expired License",
        "Grace Period Expire Date": "2026-10-10",
        "Occurred On (NT)": _epoch_ms_to_iso("1735689600000"),
        "Cleared On (NT)": None,
        "Log Serial Number": "998877",
    }


def test_license_trial_alarms_returns_null_for_missing_or_malformed_fields():
    client = FakeHuaweiClient(
        {
            "alarmInformationList": [
                {
                    "alarmId": "26817",
                    "objectInstance": "Function Type=eNodeB Function, malformed-field",
                }
            ]
        }
    )

    response = _call_license_trial_endpoint(client)

    assert response.status_code == 200
    alarm = response.json()["alarms"][0]
    assert alarm["Function Type"] == "eNodeB Function"
    assert alarm["Trial Reason"] is None
    assert alarm["Grace Period Expire Date"] is None
    assert "Location Information" not in alarm


def test_license_trial_alarms_sends_expected_query_params():
    client = FakeHuaweiClient({"alarmInformationList": [], "marker": "null"})

    response = _call_license_trial_endpoint(client, {"limit": 10, "marker": "page-1"})

    assert response.status_code == 200
    client.get.assert_awaited_once_with(
        "/api/rest/faultSupervisonManagement/v1/alarms",
        headers={"X-Auth-Token": "test-token"},
        params={
            "dataType": "CURRENT",
            "filter": _LICENSE_TRIAL_FILTER,
            "limit": 10,
            "marker": "page-1",
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


@pytest.mark.parametrize(
    ("cleared_time", "upstream_cleared", "expected_cleared"),
    [
        (None, "1", "Activa"),
        ("0", "1", "Activa"),
        ("1786552739000", "0", "Limpia"),
    ],
)
def test_site_alarm_cleared_state_comes_only_from_cleared_time(
    cleared_time, upstream_cleared, expected_cleared
):
    client = FakeHuaweiClient(
        {
            "alarmInformationList": [
                {
                    "alarmId": "1",
                    "alarmClearedTime": cleared_time,
                    "cleared": upstream_cleared,
                }
            ],
            "marker": "next-page",
        }
    )

    response = _call_alarms_endpoint("/alarms/SITE-1", client, {"limit": 10})

    assert response.status_code == 200
    alarm = response.json()["alarms"][0]
    assert alarm["alarmClearedTime"] == _epoch_ms_to_iso(cleared_time)
    assert alarm["cleared"] == expected_cleared
    assert response.json()["count"] == 1
    assert response.json()["marker"] == "next-page"
    assert client.get.await_args.kwargs["params"]["dataType"] == "CURRENT"
