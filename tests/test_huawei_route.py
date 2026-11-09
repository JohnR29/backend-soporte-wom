from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException
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


@pytest.fixture(autouse=True)
def mock_site_directory():
    async def resolve_as_existing_nodes(names, target_column):
        return [
            {"input": name, "resolved": name, "status": "resolved"}
            for name in names
        ]

    with patch(
        "app.api.routes.huawei.resolve_names",
        new=AsyncMock(side_effect=resolve_as_existing_nodes),
    ):
        yield


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
        "name_resolution": [
            {"input": "NE-001", "resolved": "NE-001", "status": "resolved"}
        ],
    }
    client.post.assert_awaited_once_with(
        "/api/rest/mmlManagement/v1/command",
        headers={"X-Auth-Token": "test-token"},
        json={"command": "display version;", "neNames": ["NE-001"]},
    )


@pytest.mark.parametrize(
    ("endpoint", "body", "upstream_call"),
    [
        (
            "/mml/command",
            {"command": "display version;", "ne_names": ["AN0069", "MBTS-AN0069", "AN0096"]},
            "command",
        ),
        (
            "/mml/cell-summary-lte",
            {"ne_names": ["AN0069", "MBTS-AN0069", "AN0096"]},
            "lte",
        ),
        (
            "/mml/cell-summary-nr",
            {"ne_names": ["AN0069", "MBTS-AN0069", "AN0096"]},
            "nr",
        ),
        (
            "/mml/kpis",
            {"ne_names": ["AN0069", "MBTS-AN0069", "AN0096"]},
            "kpis",
        ),
    ],
)
def test_4g_routes_resolve_site_and_direct_node_preserving_mixed_batch(
    endpoint, body, upstream_call
):
    async def resolve_for_test(names, target_column):
        assert target_column == "nodo"
        return [
            {
                "input": name,
                "resolved": None if name == "AN0096" else "MBTS-AN0069",
                "status": "not_found" if name == "AN0096" else "resolved",
                **({"error": "No se encontró el sitio.", "suggestions": ["AN0069"]} if name == "AN0096" else {}),
            }
            for name in names
        ]

    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(side_effect=resolve_for_test),
            ),
            patch(
                "app.api.routes.huawei._execute_mml",
                new=AsyncMock(return_value={"results": []}),
            ) as execute_mml,
            patch(
                "app.api.routes.huawei._create_measurement_task",
                new=AsyncMock(return_value={"records": []}),
            ) as create_measurement_task,
            TestClient(app) as test_client,
        ):
            response = test_client.post(endpoint, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    result = response.json()
    assert [item["input"] for item in result["name_resolution"]] == body["ne_names"]
    assert [item["status"] for item in result["name_resolution"]] == [
        "resolved",
        "resolved",
        "not_found",
    ]
    if upstream_call == "kpis":
        create_measurement_task.assert_awaited_once_with(["MBTS-AN0069", "MBTS-AN0069"])
        execute_mml.assert_not_awaited()
    else:
        expected_command = {
            "command": "display version;",
            "lte": "DSP CELL:;",
            "nr": "DSP NRCELL:;",
        }[upstream_call]
        execute_mml.assert_awaited_once_with(
            expected_command,
            ["MBTS-AN0069", "MBTS-AN0069"],
        )
        create_measurement_task.assert_not_awaited()


def test_mml_command_marks_offline_ne_as_failed_without_parsing_as_mml():
    client = FakeHuaweiClient(
        {
            "asynchId": "0501_20260827101057_12439",
            "results": [
                {
                    "name": "MBTS-RM_3G_009",
                    "report": "Ne is not connected.",
                    "result": "Failed.",
                    "retCode": -1,
                    "serialId": 0,
                }
            ],
            "retCode": "99998",
            "retMessage": "Execution failed.",
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
                json={"command": "display version;", "ne_names": ["MBTS-RM_3G_009"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["retCode"] == "99998"
    assert body["results"][0]["report"] == {"error": "Ne is not connected."}


def test_mml_command_reports_unknown_ne_as_a_failed_result():
    client = FakeHuaweiClient(
        {
            "retCode": "90018",
            "retMessage": "The following NE list is not exist: MBTS-RM_3G_0009.",
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
                json={"command": "display version;", "ne_names": ["MBTS-RM_3G_0009"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["name"] == "MBTS-RM_3G_0009"
    assert body["results"][0]["report"] == {
        "error": "NE no existe o el nombre está mal escrito."
    }


def test_mml_command_reports_unknown_ne_when_huawei_returns_http_error_with_envelope():
    error_payload = {
        "retCode": "90018",
        "retMessage": "The following NE list is not exist: MBTS-RM_3G_0009.",
    }
    client = FakeHuaweiClient(error_payload)
    client.post = AsyncMock(
        return_value=httpx.Response(
            400,
            json=error_payload,
            request=httpx.Request("POST", "https://huawei.example"),
        )
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
                json={
                    "command": "display version;",
                    "ne_names": ["MBTS-RM_3G_0009"],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["name"] == "MBTS-RM_3G_0009"
    assert body["results"][0]["report"] == {
        "error": "NE no existe o el nombre está mal escrito."
    }


def test_mml_command_returns_per_ne_result_when_mixing_operative_offline_and_unknown_ne():
    first_response = httpx.Response(
        400,
        json={
            "retCode": "90018",
            "retMessage": "The following NE list is not exist: MBTS-RM35444.",
        },
        request=httpx.Request("POST", "https://huawei.example"),
    )
    second_response = httpx.Response(
        200,
        json={
            "asynchId": "0501_20260827101057_12440",
            "results": [
                {
                    "name": "MBTS-RM_3G_009",
                    "report": "Ne is not connected.",
                    "result": "Failed.",
                    "retCode": -1,
                    "serialId": 0,
                },
                {
                    "name": "MBTS-RM_OK",
                    "report": "RETCODE = 0\nnot complete",
                    "result": "Operation succeeded.",
                    "retCode": 0,
                    "serialId": 1,
                },
            ],
            "retCode": "99998",
            "retMessage": "Execution failed.",
        },
        request=httpx.Request("POST", "https://huawei.example"),
    )
    client = FakeHuaweiClient({})
    client.post = AsyncMock(side_effect=[first_response, second_response])
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
                json={
                    "command": "display version;",
                    "ne_names": ["MBTS-RM_OK", "MBTS-RM_3G_009", "MBTS-RM35444"],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [result["name"] for result in body["results"]] == [
        "MBTS-RM_OK",
        "MBTS-RM_3G_009",
        "MBTS-RM35444",
    ]
    results_by_name = {result["name"]: result for result in body["results"]}
    assert results_by_name["MBTS-RM_3G_009"]["report"] == {"error": "Ne is not connected."}
    assert results_by_name["MBTS-RM35444"]["report"] == {
        "error": "NE no existe o el nombre está mal escrito."
    }
    assert results_by_name["MBTS-RM_OK"]["retCode"] == 0
    assert client.post.await_count == 2
    second_call_kwargs = client.post.await_args_list[1].kwargs
    assert second_call_kwargs["json"]["neNames"] == ["MBTS-RM_OK", "MBTS-RM_3G_009"]


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
        "name_resolution": [
            {"input": "NE-001", "resolved": "NE-001", "status": "resolved"}
        ],
    }


def test_cell_summary_runs_two_commands_and_joins_by_local_cell_id():
    dsp_report = """+++ NE-001 2026-08-23 10:20:30
RETCODE = 0
---
Local Cell ID  Cell Name  Cell instance state  Maximum transmit power(0.1dBm)

1  cell-a  ACTIVE  430
2  cell-b  LOCKED  400
(Number of results = 2)
---    END"""
    lst_report = """+++ NE-001 2026-08-23 10:21:30
RETCODE = 0
---
Local Cell ID  Frequency band  Downlink EARFCN

1  LTE  1800
(Number of results = 1)
---    END"""
    dsp_report_ne2 = dsp_report.replace("NE-001", "NE-002")
    lst_report_ne2 = lst_report.replace("NE-001", "NE-002").replace(
        "1  LTE  1800", "1  NR  3500"
    )
    responses = iter([
        {
            "results": [
                {"name": "NE-001", "report": dsp_report},
                {"name": "NE-002", "report": dsp_report_ne2},
            ]
        },
        {
            "results": [
                {"name": "NE-001", "report": lst_report},
                {"name": "NE-002", "report": lst_report_ne2},
            ]
        },
    ])
    client = FakeHuaweiClient({})
    client.post.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json=next(responses),
        request=httpx.Request("POST", "https://huawei.example"),
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
                "/mml/cell-summary-lte",
                json={"ne_names": ["NE-001", "NE-002"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"commands", "records", "count", "errors", "name_resolution"}
    assert isinstance(body["commands"], list)
    assert isinstance(body["count"], int)
    assert isinstance(body["errors"], list)
    assert isinstance(body["name_resolution"], list)
    assert response.json()["records"] == [
        {
            "ne_name": "NE-001",
            "Local Cell ID": "1",
            "Cell Name": "cell-a",
            "Cell instance state": "ACTIVE",
            "Maximum transmit power(0.1dBm)": "430",
            "Frequency band": "LTE",
            "Downlink EARFCN": "1800",
        },
        {
            "ne_name": "NE-001",
            "Local Cell ID": "2",
            "Cell Name": "cell-b",
            "Cell instance state": "LOCKED",
            "Maximum transmit power(0.1dBm)": "400",
            "Frequency band": None,
            "Downlink EARFCN": None,
        },
        {
            "ne_name": "NE-002",
            "Local Cell ID": "1",
            "Cell Name": "cell-a",
            "Cell instance state": "ACTIVE",
            "Maximum transmit power(0.1dBm)": "430",
            "Frequency band": "NR",
            "Downlink EARFCN": "3500",
        },
        {
            "ne_name": "NE-002",
            "Local Cell ID": "2",
            "Cell Name": "cell-b",
            "Cell instance state": "LOCKED",
            "Maximum transmit power(0.1dBm)": "400",
            "Frequency band": None,
            "Downlink EARFCN": None,
        },
    ]
    assert [call.kwargs["json"]["command"] for call in client.post.await_args_list] == [
        "DSP CELL:;",
        "LST CELL:;",
    ]


def test_cell_summary_lte_reports_offline_ne_as_error_without_dropping_it():
    dsp_report = """+++ NE-001 2026-08-23 10:20:30
RETCODE = 0
---
Local Cell ID  Cell Name  Cell instance state  Maximum transmit power(0.1dBm)

1  cell-a  ACTIVE  430
(Number of results = 1)
---    END"""
    lst_report = """+++ NE-001 2026-08-23 10:21:30
RETCODE = 0
---
Local Cell ID  Frequency band  Downlink EARFCN

1  LTE  1800
(Number of results = 1)
---    END"""
    responses = iter([
        {
            "results": [
                {"name": "NE-001", "report": dsp_report},
                {
                    "name": "NE-OFFLINE",
                    "report": "Ne is not connected.",
                    "result": "Failed.",
                    "retCode": -1,
                },
            ]
        },
        {
            "results": [
                {"name": "NE-001", "report": lst_report},
                {
                    "name": "NE-OFFLINE",
                    "report": "Ne is not connected.",
                    "result": "Failed.",
                    "retCode": -1,
                },
            ]
        },
    ])
    client = FakeHuaweiClient({})
    client.post.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json=next(responses),
        request=httpx.Request("POST", "https://huawei.example"),
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
                "/mml/cell-summary-lte",
                json={"ne_names": ["NE-001", "NE-OFFLINE"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [record["ne_name"] for record in body["records"]] == ["NE-001"]
    assert body["errors"] == [
        {
            "code": "NODE_DISCONNECTED",
            "message": "Nodo desconectado.",
            "input": "NE-OFFLINE",
            "ne_name": "NE-OFFLINE",
            "error": "Ne is not connected.",
        }
    ]


@pytest.mark.parametrize(
    ("endpoint", "commands"),
    [
        ("/mml/cell-summary-lte", ["DSP CELL:;"]),
        ("/mml/cell-summary-nr", ["DSP NRCELL:;"]),
    ],
)
def test_cell_summary_single_offline_ne_returns_200_with_errors(endpoint, commands):
    client = FakeHuaweiClient({})
    client.post.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json={
            "results": [
                {
                    "name": "NE-OFFLINE",
                    "report": "Ne is not connected.",
                    "result": "Failed.",
                    "retCode": -1,
                }
            ]
        },
        request=httpx.Request("POST", "https://huawei.example"),
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
            response = test_client.post(endpoint, json={"ne_names": ["NE-OFFLINE"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["commands"] == commands
    assert body["records"] == []
    assert body["count"] == 0
    assert body["errors"] == [
        {
            "code": "NODE_DISCONNECTED",
            "message": "Nodo desconectado.",
            "input": "NE-OFFLINE",
            "ne_name": "NE-OFFLINE",
            "error": "Ne is not connected.",
        }
    ]


def test_nr_cell_summary_joins_three_commands_by_node_and_cell_id():
    nrcell_report = """+++ NE-001 2026-08-23 10:20:30
RETCODE = 0
---
NR Cell ID  Cell Name  Cell Available State

1  nr-cell-a  Available
(Number of results = 1)
---    END"""
    nrducell_report = """+++ NE-001 2026-08-23 10:21:30
RETCODE = 0
---
Cell ID  Frequency Band  Downlink NARFCN

1  n78  640000
(Number of results = 1)
---    END"""
    nrducelltrp_report = """+++ NE-001 2026-08-23 10:22:30
RETCODE = 0
---
NR DU Cell ID  Max Transmit Power(0.1dBm)

1  320
(Number of results = 1)
---    END"""
    responses = iter([
        {
            "results": [
                {"name": "NE-001", "report": nrcell_report},
                {"name": "NE-002", "report": nrcell_report.replace("NE-001", "NE-002")},
            ]
        },
        {
            "results": [
                {"name": "NE-001", "report": nrducell_report},
                {"name": "NE-002", "report": nrducell_report.replace("NE-001", "NE-002").replace("640000", "641000")},
            ]
        },
        {
            "results": [
                {"name": "NE-001", "report": nrducelltrp_report},
                {"name": "NE-002", "report": nrducelltrp_report.replace("NE-001", "NE-002").replace("320", "330")},
            ]
        },
    ])
    client = FakeHuaweiClient({})
    client.post.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json=next(responses),
        request=httpx.Request("POST", "https://huawei.example"),
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
                "/mml/cell-summary-nr",
                json={"ne_names": ["NE-001", "NE-002"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"commands", "records", "count", "errors", "name_resolution"}
    assert isinstance(body["count"], int)
    assert isinstance(body["errors"], list)
    records = body["records"]
    assert records[0]["ne_name"] == "NE-001"
    assert records[0]["NR Cell ID"] == "1"
    assert records[0]["Frequency Band"] == "n78"
    assert records[0]["Downlink NARFCN"] == "640000"
    assert "NR DU Cell ID" not in records[0]
    assert records[0]["Max Transmit Power(0.1dBm)"] == "320"
    assert records[1]["ne_name"] == "NE-002"
    assert records[1]["Downlink NARFCN"] == "641000"
    assert records[1]["Max Transmit Power(0.1dBm)"] == "330"
    assert [call.kwargs["json"]["command"] for call in client.post.await_args_list] == [
        "DSP NRCELL:;",
        "LST NRDUCELL:;",
        "LST NRDUCELLTRP:;",
    ]


_TEST_RNC_NAMES = ["STG03", "STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01"]


def _umts_fail_result(name: str) -> dict:
    return {
        "name": name,
        "report": "RETCODE = 235308841  NodeB is not configured",
        "result": "NodeB is not configured",
        "retCode": 235308841,
        "serialId": -1,
    }


def test_cell_summary_umts_finds_owning_rnc_and_joins_by_cell_id():
    dsp_report = """+++ STG03 2026-08-31 10:45:04
RETCODE = 0
---
Cell ID  Cell name  Operation state

501  URM3644_1_B1  Available
502  URM3644_2_B1  Available
503  URM3644_3_B1  Available
(Number of results = 3)
---    END"""
    lst_report = """+++ STG03 2026-08-31 10:50:00
RETCODE = 0
---
Cell ID  Max Transmit Power of Cell  Band Indicator  Downlink UARFCN

501  430  BAND1  10787
502  430  BAND1  10787
503  430  BAND1  10787
(Number of results = 3)
---    END"""
    dsp_results = [_umts_fail_result(name) for name in ["STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01"]]
    dsp_results.insert(0, {"name": "STG03", "report": dsp_report, "result": "Execution succeeded.", "retCode": 0, "serialId": -1})
    responses = iter([
        {"results": dsp_results},
        {"results": [{"name": "STG03", "report": lst_report, "result": "Execution succeeded.", "retCode": 0, "serialId": -1}]},
    ])
    client = FakeHuaweiClient({})
    client.post.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json=next(responses),
        request=httpx.Request("POST", "https://huawei.example"),
    )
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            patch("app.api.routes.huawei._umts_rnc_names", return_value=_TEST_RNC_NAMES),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": "URM3644"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["rnc_names_matched"] == ["STG03"]
    assert body["pattern"] == "URM3644"
    assert body["count"] == 3
    assert body["errors"] == [
        {
            "code": None,
            "message": "Error en otro controlador.",
            "input": "URM3644",
            "ne_name": name,
            "error": "NodeB is not configured",
        }
        for name in ["STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01"]
    ]
    assert body["records"][0] == {
        "ne_name": "STG03",
        "Cell ID": "501",
        "Cell name": "URM3644_1_B1",
        "Operation state": "Available",
        "Max Transmit Power of Cell": "430",
        "Band Indicator": "BAND1",
        "Downlink UARFCN": "10787",
    }
    first_call, second_call = client.post.await_args_list
    assert first_call.kwargs["json"] == {
        "command": 'DSP UCELL:DSPT=BYNODEB,NODEBNAME="URM3644";',
        "neNames": ["STG03", "STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01"],
    }
    assert second_call.kwargs["json"] == {
        "command": 'LST UCELL:LSTTYPE=ByCellName,CELLNAME="URM3644";',
        "neNames": ["STG03"],
    }


def test_cell_summary_umts_returns_empty_records_when_no_rnc_matches():
    dsp_results = [
        _umts_fail_result(name)
        for name in ["STG03", "STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01"]
    ]
    client = FakeHuaweiClient({"results": dsp_results})
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            patch("app.api.routes.huawei._umts_rnc_names", return_value=_TEST_RNC_NAMES),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": "URM9999"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "nodeb_name": "URM9999",
        "rnc_names_matched": [],
        "pattern": None,
        "commands": ['DSP UCELL:DSPT=BYNODEB,NODEBNAME="URM9999";'],
        "records": [],
        "count": 0,
        "errors": [
            {
                "code": "NODE_NOT_FOUND",
                "message": "No se encontró el nodo URM9999.",
                "input": "URM9999",
                "ne_name": "URM9999",
                "error": "RETCODE = 235308841  NodeB is not configured",
            }
        ],
        "name_resolution": [
            {"input": "URM9999", "resolved": "URM9999", "status": "resolved"}
        ],
    }
    client.post.assert_awaited_once()


def test_cell_summary_umts_single_cell_nodeb_uses_first_token_as_pattern():
    dsp_report = """+++ STG03 2026-08-31 10:45:04
RETCODE = 0
---
Cell ID  Cell name  Operation state

901  URM9999_1_B1  Available
(Number of results = 1)
---    END"""
    lst_report = """+++ STG03 2026-08-31 10:50:00
RETCODE = 0
---
Cell ID  Max Transmit Power of Cell  Band Indicator  Downlink UARFCN

901  430  BAND1  10787
(Number of results = 1)
---    END"""
    dsp_results = [_umts_fail_result(name) for name in ["STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01"]]
    dsp_results.insert(0, {"name": "STG03", "report": dsp_report, "result": "Execution succeeded.", "retCode": 0, "serialId": -1})
    responses = iter([
        {"results": dsp_results},
        {"results": [{"name": "STG03", "report": lst_report, "result": "Execution succeeded.", "retCode": 0, "serialId": -1}]},
    ])
    client = FakeHuaweiClient({})
    client.post.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json=next(responses),
        request=httpx.Request("POST", "https://huawei.example"),
    )
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            patch("app.api.routes.huawei._umts_rnc_names", return_value=_TEST_RNC_NAMES),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": "URM9999"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["pattern"] == "URM9999"
    assert body["rnc_names_matched"] == ["STG03"]
    assert body["count"] == 1


@pytest.mark.parametrize("input_name", ["AN0069", "UAN0069"])
def test_umts_resolves_site_and_direct_nodeb_to_canonical_name(input_name):
    resolved = {
        "input": input_name,
        "resolved": "UAN0069",
        "status": "resolved",
    }
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=[resolved]),
            ) as resolve,
            patch(
                "app.api.routes.huawei._execute_mml",
                new=AsyncMock(return_value={"results": []}),
            ) as execute_mml,
            patch("app.api.routes.huawei._umts_rnc_names", return_value=_TEST_RNC_NAMES),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": input_name},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["nodeb_name"] == "UAN0069"
    assert response.json()["name_resolution"] == [resolved]
    resolve.assert_awaited_once_with([input_name], "nodeb")
    execute_mml.assert_awaited_once_with(
        'DSP UCELL:DSPT=BYNODEB,NODEBNAME="UAN0069";',
        _TEST_RNC_NAMES,
    )


@pytest.mark.parametrize(
    ("resolution", "expected_code"),
    [
        (
            {
                "input": "AN0096",
                "resolved": None,
                "status": "not_found",
                "error": "No se encontró el sitio.",
                "suggestions": ["AN0069"],
            },
            "NODE_NOT_FOUND",
        ),
        (
            {
                "input": "AN0070",
                "resolved": None,
                "status": "missing_mapping",
                "error": "El sitio no tiene mapeo para nodeb.",
            },
            "TECHNOLOGY_UNAVAILABLE",
        ),
    ],
)
def test_umts_returns_stable_resolution_errors_without_calling_huawei(
    resolution, expected_code
):
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=[resolution]),
            ),
            patch("app.api.routes.huawei._execute_mml", new=AsyncMock()) as execute_mml,
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": resolution["input"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    execute_mml.assert_not_awaited()
    error = response.json()["errors"][0]
    assert error["code"] == expected_code
    assert error["input"] == resolution["input"]
    if expected_code == "NODE_NOT_FOUND":
        assert error["suggestions"] == ["AN0069"]
    else:
        assert error["ne_name"] is None


@pytest.mark.parametrize(
    ("endpoint", "body", "target_column"),
    [
        ("/mml/cell-summary-umts", {"nodeb_name": "AN0096"}, "nodeb"),
        ("/mml/cell-summary-lte", {"ne_names": ["AN0096"]}, "nodo"),
        ("/mml/cell-summary-nr", {"ne_names": ["AN0096"]}, "nodo"),
    ],
)
def test_state_routes_return_node_not_found_for_unresolved_names(
    endpoint, body, target_column
):
    input_name = body.get("nodeb_name") or body["ne_names"][0]
    resolution = {
        "input": input_name,
        "resolved": None,
        "status": "not_found",
        "error": "No se encontró el sitio.",
        "suggestions": ["AN0069"],
    }
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=[resolution]),
            ) as resolve,
            patch("app.api.routes.huawei._execute_mml", new=AsyncMock()) as execute_mml,
            TestClient(app) as test_client,
        ):
            response = test_client.post(endpoint, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    result = response.json()
    assert result["records"] == []
    assert result["count"] == 0
    assert result["name_resolution"] == [resolution]
    assert result["errors"] == [
        {
            "code": "NODE_NOT_FOUND",
            "message": f"No se encontró el nodo {input_name}.",
            "input": input_name,
            "ne_name": None,
            "suggestions": ["AN0069"],
        }
    ]
    resolve.assert_awaited_once_with([input_name], target_column)
    execute_mml.assert_not_awaited()


def test_umts_returns_service_unavailable_when_directory_cannot_be_queried():
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(
                    side_effect=HTTPException(
                        status_code=503,
                        detail="El directorio de sitios no está configurado o disponible.",
                    )
                ),
            ),
            patch("app.api.routes.huawei._execute_mml", new=AsyncMock()) as execute_mml,
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": "AN0069"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    execute_mml.assert_not_awaited()


def test_4g_batch_skips_ambiguous_site_and_keeps_resolved_names():
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(
                    return_value=[
                        {"input": "AN0069", "resolved": "MBTS-AN0069", "status": "resolved"},
                        {
                            "input": "RM173",
                            "resolved": None,
                            "status": "ambiguous_mapping",
                            "error": "El sitio tiene múltiples mapeos para nodo.",
                        },
                    ]
                ),
            ),
            patch(
                "app.api.routes.huawei._execute_mml",
                new=AsyncMock(return_value={"results": []}),
            ) as execute_mml,
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/command",
                json={"command": "display version;", "ne_names": ["AN0069", "RM173"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name_resolution"][1]["status"] == "ambiguous_mapping"
    execute_mml.assert_awaited_once_with("display version;", ["MBTS-AN0069"])


def test_umts_rejects_ambiguous_nodeb_mapping_without_calling_huawei():
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(
                    return_value=[
                        {
                            "input": "RM173",
                            "resolved": None,
                            "status": "ambiguous_mapping",
                            "error": "El sitio tiene múltiples mapeos para nodeb.",
                        }
                    ]
                ),
            ),
            patch("app.api.routes.huawei._execute_mml", new=AsyncMock()) as execute_mml,
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts",
                json={"nodeb_name": "RM173"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["errors"][0]["code"] == "TECHNOLOGY_UNAVAILABLE"
    execute_mml.assert_not_awaited()


class FakeHuaweiGetClient:
    def __init__(self, response: httpx.Response):
        self.get = AsyncMock(return_value=response)


def test_get_site_alarms_returns_simplified_and_translated_fields():
    payload = {
        "alarmInformationList": [
            {
                "alarmId": "29841",
                "objectInstance": "gNodeB Function Name=NOH8315, NR Cell ID=1",
                "notificationType": "notifyChangedClearedAlarm",
                "alarmRaisedTime": "1786552439000",
                "alarmClearedTime": "1786552739000",
                "alarmType": "3",
                "probableCause": "",
                "perceivedSeverity": "2",
                "additionalInformation": "RAT_INFO=U-L-N, AFFECTED_RAT=N",
                "ackTime": "1786552919418",
                "ackUserId": "< System operator >",
                "ackState": "1",
                "clearUserId": "< NE operator >",
                "cleared": "1",
                "meName": "MBTS-OH8315",
                "productName": "BTS3900",
                "alarmName": "NR Cell Unavailable",
                "nativeMoName": "gNodeB Function Name=NOH8315, NR Cell ID=1",
                "csn": "1081088916",
                "subCsn": "4828",
                "specialAlarmStatus": "0",
                "comments": "",
                "nativeMeDn": "NE=8143",
                "vflag": "0",
            }
        ],
        "marker": None,
        "retCode": "90000",
        "retMessage": "Operation succeeded.",
    }
    client = FakeHuaweiGetClient(
        httpx.Response(200, json=payload, request=httpx.Request("GET", "https://huawei.example"))
    )
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
            response = test_client.get("/alarms/MBTS-OH8315")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["site_name"] == "MBTS-OH8315"
    assert body["count"] == 1
    assert body["marker"] is None
    assert body["alarms"][0] == {
        "alarmId": "29841",
        "alarmName": "NR Cell Unavailable",
        "meName": "MBTS-OH8315",
        "objectInstance": "gNodeB Function Name=NOH8315, NR Cell ID=1",
        "perceivedSeverity": "Mayor",
        "alarmRaisedTime": "2026-08-12T12:33:59-04:00",
        "alarmClearedTime": "2026-08-12T12:38:59-04:00",
        "cleared": "Limpia",
        "ackState": "Reconocida",
        "comments": "",
        "additionalInformation": "RAT_INFO=U-L-N, AFFECTED_RAT=N",
    }
    client.get.assert_awaited_once_with(
        "/api/rest/faultSupervisonManagement/v1/alarms",
        headers={"X-Auth-Token": "test-token"},
        params={"dataType": "CURRENT", "baseObjectInstance": "MBTS-OH8315", "limit": 500},
    )


def test_get_site_alarms_forwards_marker_and_falls_back_on_unknown_codes():
    payload = {
        "alarmInformationList": [
            {
                "alarmId": "1",
                "alarmName": "Unknown Alarm",
                "meName": "MBTS-OH8315",
                "objectInstance": "obj",
                "perceivedSeverity": "9",
                "alarmRaisedTime": "1786552439000",
                "alarmClearedTime": None,
                "cleared": "9",
                "ackState": "9",
                "comments": "",
                "additionalInformation": "",
            }
        ],
        "marker": "next-page-token",
        "retCode": "90000",
        "retMessage": "Operation succeeded.",
    }
    client = FakeHuaweiGetClient(
        httpx.Response(200, json=payload, request=httpx.Request("GET", "https://huawei.example"))
    )
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
            response = test_client.get("/alarms/MBTS-OH8315?limit=10&marker=prev-token")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["marker"] == "next-page-token"
    assert body["alarms"][0]["perceivedSeverity"] == "9"
    assert body["alarms"][0]["cleared"] == "Activa"
    assert body["alarms"][0]["ackState"] == "9"
    assert body["alarms"][0]["alarmClearedTime"] is None
    client.get.assert_awaited_once_with(
        "/api/rest/faultSupervisonManagement/v1/alarms",
        headers={"X-Auth-Token": "test-token"},
        params={"dataType": "CURRENT", "baseObjectInstance": "MBTS-OH8315", "limit": 10, "marker": "prev-token"},
    )


def test_get_site_alarms_treats_epoch_zero_cleared_time_as_none_for_active_alarms():
    payload = {
        "alarmInformationList": [
            {
                "alarmId": "2",
                "alarmName": "Active Alarm",
                "meName": "MBTS-OH8315",
                "objectInstance": "obj",
                "perceivedSeverity": "1",
                "alarmRaisedTime": "1786552439000",
                "alarmClearedTime": "0",
                "cleared": "0",
                "ackState": "0",
                "comments": "",
                "additionalInformation": "",
            }
        ],
        "marker": None,
        "retCode": "90000",
        "retMessage": "Operation succeeded.",
    }
    client = FakeHuaweiGetClient(
        httpx.Response(200, json=payload, request=httpx.Request("GET", "https://huawei.example"))
    )
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
            response = test_client.get("/alarms/MBTS-OH8315")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["alarms"][0]["alarmClearedTime"] is None


def test_get_site_alarms_maps_huawei_error_envelope_to_400():
    error_payload = {"retCode": "90026", "retMessage": "Invalid parameter value."}
    client = FakeHuaweiGetClient(
        httpx.Response(400, json=error_payload, request=httpx.Request("GET", "https://huawei.example"))
    )
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
            response = test_client.get("/alarms/MBTS-OH8315")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid parameter value."


def test_get_site_alarms_maps_proxy_error_to_502():
    client = FakeHuaweiGetClient(httpx.Response(200, json={}, request=httpx.Request("GET", "https://huawei.example")))
    client.get = AsyncMock(side_effect=httpx.ProxyError("blocked"))
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
            response = test_client.get("/alarms/MBTS-OH8315")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502


class FakeHuaweiPmClient:
    def __init__(self, post_response: httpx.Response, get_responses: list[httpx.Response] | None = None):
        self.post = AsyncMock(return_value=post_response)
        self.get = AsyncMock(side_effect=get_responses or [])


def _chile_time(utc_string: str) -> str:
    """Expected value of _utc_string_to_chile_time for a given UTC 'Z' string."""
    utc_dt = datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(ZoneInfo("America/Santiago")).strftime("%Y-%m-%dT%H:%M:%S")


def test_get_measurement_kpis_sends_fixed_params_and_flattens_result():
    result_item = {
        "startTime": "2026-08-31T03:00:00Z",
        "neName": "MBTS-RM3644",
        "objectName": {"Cell Name": "L4RM3644_1", "Local Cell ID": "0"},
        "counterValues": ["100", "50", "25.2", "10"],
    }
    payload = {"result": [result_item], "marker": None, "retCode": "90000"}
    client = FakeHuaweiPmClient(
        httpx.Response(200, json=payload, request=httpx.Request("POST", "https://huawei.example"))
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
            response = test_client.post("/mml/kpis", json={"ne_names": ["MBTS-RM3644"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "records": [
            {
                "startTime": _chile_time("2026-08-31T03:00:00Z"),
                "neName": "MBTS-RM3644",
                "Cell Name": "L4RM3644_1",
                "Local Cell ID": "0",
                "ERAB Success Rate": "100",
                "User Max": "50",
                "Traffic": "25.2",
                "Throughput": "10",
            }
        ],
        "name_resolution": [
            {"input": "MBTS-RM3644", "resolved": "MBTS-RM3644", "status": "resolved"}
        ],
        "errors": [],
    }

    client.post.assert_awaited_once()
    _, kwargs = client.post.call_args
    body = kwargs["json"]
    assert body["timeFormat"] == "utcTimeString"
    assert body["period"] == 60
    assert body["counterIds"] == [1543503856, 1543503857, 1543503836, 1543503845]
    assert body["isQueryAllNe"] == 0
    assert body["neTypeName"] == "eNodeB"
    assert body["neNames"] == ["MBTS-RM3644"]

    start = datetime.strptime(body["startTime"], "%Y-%m-%dT%H:%M:%SZ")
    end = datetime.strptime(body["endTime"], "%Y-%m-%dT%H:%M:%SZ")
    assert end - start == timedelta(hours=24)
    assert start.minute == 0 and start.second == 0
    assert end.minute == 0 and end.second == 0


def test_get_measurement_kpis_polls_async_task_and_flattens_merged_result():
    accepted_payload = {"retCode": "90037", "taskId": "1"}
    running_payload = {"retCode": "90037"}
    result_item = {
        "startTime": "2026-08-31T04:00:00Z",
        "neName": "MBTS-RM3644",
        "objectName": {"Cell Name": "L4RM3644_2", "Local Cell ID": "1"},
        "counterValues": ["99.8", "38", "41.43", "8.4"],
    }
    final_payload = {"result": [result_item], "marker": None, "retCode": "90000"}
    client = FakeHuaweiPmClient(
        httpx.Response(202, json=accepted_payload, request=httpx.Request("POST", "https://huawei.example")),
        [
            httpx.Response(200, json=running_payload, request=httpx.Request("GET", "https://huawei.example")),
            httpx.Response(200, json=final_payload, request=httpx.Request("GET", "https://huawei.example")),
        ],
    )
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            patch("app.api.routes.huawei.asyncio_sleep", new=AsyncMock()),
            TestClient(app) as test_client,
        ):
            response = test_client.post("/mml/kpis", json={"ne_names": ["MBTS-RM3644"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "records": [
            {
                "startTime": _chile_time("2026-08-31T04:00:00Z"),
                "neName": "MBTS-RM3644",
                "Cell Name": "L4RM3644_2",
                "Local Cell ID": "1",
                "ERAB Success Rate": "99.8",
                "User Max": "38",
                "Traffic": "41.43",
                "Throughput": "8.4",
            }
        ],
        "name_resolution": [
            {"input": "MBTS-RM3644", "resolved": "MBTS-RM3644", "status": "resolved"}
        ],
        "errors": [],
    }
    assert client.get.await_count == 2
    client.get.assert_awaited_with(
        "/api/rest/performanceManagement/v2/measurementResults/1",
        headers={"X-Auth-Token": "test-token"},
        params={"limit": 1000},
    )



class FakeScriptClient:
    """Routes Huawei MML script task calls by method/path suffix."""

    def __init__(self, fail_upload_for=None):
        self.calls = []
        self.fail_upload_for = fail_upload_for

    async def request(self, method, path, headers=None, data=None, files=None, **kwargs):
        self.calls.append((method, path))
        req = httpx.Request(method, "https://huawei.example" + path)
        if method == "POST":
            name = data["taskName"]
            if name == self.fail_upload_for:
                return httpx.Response(400, json={"retCode": "1", "retMessage": "bad script"}, request=req)
            return httpx.Response(200, json={"taskId": f"id-{name}"}, request=req)
        if path.endswith("/status"):
            return httpx.Response(200, json={"currentState": 3}, request=req)
        if path.endswith("/result"):
            return httpx.Response(200, text=f"result of {path.split('/')[-2]}", request=req)
        return httpx.Response(200, json={}, request=req)


def _post_scripts(client, files):
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "t"}),
            ),
            TestClient(app) as test_client,
        ):
            return test_client.post("/mml/scripts", files=files)
    finally:
        app.dependency_overrides.clear()


def test_mml_scripts_runs_each_file_and_deletes_tasks():
    client = FakeScriptClient()
    response = _post_scripts(
        client,
        [("files", ("a.txt", b"LST VER:;", "text/plain")), ("files", ("b.txt", b"LST NE:;", "text/plain"))],
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["ok", "ok"]
    assert results[0]["result"] == "result of id-a"
    assert ("DELETE", "/api/rest/mmlManagement/v1/tasks/id-a") in client.calls
    assert ("DELETE", "/api/rest/mmlManagement/v1/tasks/id-b") in client.calls


def test_mml_scripts_one_failure_does_not_affect_others():
    client = FakeScriptClient(fail_upload_for="bad")
    response = _post_scripts(
        client,
        [("files", ("bad.txt", b"x", "text/plain")), ("files", ("ok.txt", b"LST VER:;", "text/plain"))],
    )

    results = response.json()["results"]
    assert results[0]["status"] == "failed"
    assert results[0]["error"] == "bad script"
    assert results[1]["status"] == "ok"


def test_mml_scripts_rejects_oversized_and_empty_files():
    client = FakeScriptClient()
    big = _post_scripts(client, [("files", ("big.txt", b"x" * (2 * 1024 * 1024 + 1), "text/plain"))])
    empty = _post_scripts(client, [("files", ("e.txt", b"  ", "text/plain"))])

    assert big.status_code == 422
    assert empty.status_code == 422
    assert client.calls == []


def test_mml_scripts_txt_and_zip_downloads():
    import io, zipfile

    files = [("files", ("a.txt", b"LST VER:;", "text/plain")), ("files", ("b.txt", b"LST NE:;", "text/plain"))]

    def post(output):
        app.dependency_overrides[require_user] = lambda: "operator-1"
        try:
            with (
                patch("app.api.routes.huawei.get_client", return_value=FakeScriptClient()),
                patch("app.api.routes.huawei.get_huawei_headers", new=AsyncMock(return_value={})),
                TestClient(app) as c,
            ):
                return c.post("/mml/scripts", files=files, data={"output": output})
        finally:
            app.dependency_overrides.clear()

    txt = post("txt")
    assert txt.headers["content-type"].startswith("text/plain")
    assert "===== a.txt =====\nresult of id-a" in txt.text

    archive = zipfile.ZipFile(io.BytesIO(post("zip").content))
    assert archive.namelist() == ["01_a_resultado.txt", "02_b_resultado.txt"]
    assert archive.read("01_a_resultado.txt") == b"result of id-a"


def test_kpis_return_unresolved_errors_and_preserve_resolved_measurements():
    resolutions = [
        {
            "input": "UNKNOWN",
            "resolved": None,
            "status": "not_found",
            "error": "No se encontró el sitio.",
            "suggestions": ["SITE-1"],
        },
        {"input": "SITE-1", "resolved": "ENB-1", "status": "resolved"},
        {"input": "SITE-2", "resolved": "ENB-2", "status": "resolved"},
    ]
    records = [{"neName": "ENB-1", "startTime": "2026-11-09T10:00:00"}]
    create_measurement_task = AsyncMock(return_value={"records": records})
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=resolutions),
            ),
            patch(
                "app.api.routes.huawei._create_measurement_task",
                new=create_measurement_task,
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/kpis",
                json={
                    "ne_names": ["UNKNOWN", "SITE-1", "SITE-2"],
                    "period_start": "2000-01-01",
                    "period_end": "2000-01-02",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["records"] == records
    assert body["name_resolution"] == resolutions
    assert body["errors"] == [
        {
            "code": "NODE_NOT_FOUND",
            "message": "No se encontró el nodo UNKNOWN.",
            "input": "UNKNOWN",
            "ne_name": None,
            "suggestions": ["SITE-1"],
        }
    ]
    create_measurement_task.assert_awaited_once_with(["ENB-1", "ENB-2"])


def test_kpis_ignore_caller_period_and_keep_empty_resolved_nodes_error_free():
    client = FakeHuaweiClient({"result": [], "retCode": "90000"})
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei._last_24h_window",
                return_value=("2026-11-08T00:00:00Z", "2026-11-09T00:00:00Z"),
            ),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": "test-token"}),
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/kpis",
                json={
                    "ne_names": ["ENB-1"],
                    "period_start": "2000-01-01T00:00:00Z",
                    "period_end": "2000-01-02T00:00:00Z",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["records"] == []
    assert response.json()["errors"] == []
    query = client.post.await_args.kwargs["json"]
    assert query["startTime"] == "2026-11-08T00:00:00Z"
    assert query["endTime"] == "2026-11-09T00:00:00Z"
    assert "period_start" not in query
    assert "period_end" not in query


def test_kpis_return_errors_without_calling_huawei_when_all_names_are_unresolved():
    resolution = {
        "input": "UNKNOWN",
        "resolved": None,
        "status": "not_found",
        "error": "No se encontró el sitio.",
        "suggestions": [],
    }
    create_measurement_task = AsyncMock()
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=[resolution]),
            ),
            patch(
                "app.api.routes.huawei._create_measurement_task",
                new=create_measurement_task,
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post("/mml/kpis", json={"ne_names": ["UNKNOWN"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["records"] == []
    assert response.json()["errors"][0]["code"] == "NODE_NOT_FOUND"
    create_measurement_task.assert_not_awaited()


def test_kpi_response_and_logs_do_not_expose_huawei_token(caplog):
    sentinel_token = "IN_MEMORY_HUAWEI_TOKEN_SENTINEL"
    client = FakeHuaweiClient({"result": [], "retCode": "90000"})
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei.get_client", return_value=client),
            patch(
                "app.api.routes.huawei.get_huawei_headers",
                new=AsyncMock(return_value={"X-Auth-Token": sentinel_token}),
            ),
            TestClient(app) as test_client,
        ):
            response = test_client.post("/mml/kpis", json={"ne_names": ["ENB-1"]})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert sentinel_token not in response.text
    assert sentinel_token not in caplog.text


def test_nr_mixed_batch_preserves_valid_records_and_classifies_disconnected_node():
    payloads = {
        "DSP NRCELL:;": {
            "results": [
                {
                    "name": "NE-OK",
                    "report": {
                        "records": [
                            {
                                "NR Cell ID": "1",
                                "Cell Name": "nr-cell-1",
                                "Cell Available State": "Available",
                            }
                        ]
                    },
                },
                {"name": "NE-OFFLINE", "report": {"error": "Ne is not connected."}},
            ]
        },
        "LST NRDUCELL:;": {
            "results": [
                {
                    "name": "NE-OK",
                    "report": {
                        "records": [
                            {"Cell ID": "1", "Frequency Band": "n78", "Downlink NARFCN": "640000"}
                        ]
                    },
                },
                {"name": "NE-OFFLINE", "report": {"error": "Ne is not connected."}},
            ]
        },
        "LST NRDUCELLTRP:;": {
            "results": [
                {
                    "name": "NE-OK",
                    "report": {
                        "records": [
                            {"NR DU Cell ID": "1", "Max Transmit Power(0.1dBm)": "320"}
                        ]
                    },
                },
                {"name": "NE-OFFLINE", "report": {"error": "Ne is not connected."}},
            ]
        },
    }
    execute_mml = AsyncMock(side_effect=lambda command, names: payloads[command])
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch("app.api.routes.huawei._execute_mml", new=execute_mml),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-nr",
                json={"ne_names": ["NE-OK", "NE-OFFLINE"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert [record["ne_name"] for record in body["records"]] == ["NE-OK"]
    assert body["errors"] == [
        {
            "code": "NODE_DISCONNECTED",
            "message": "Nodo desconectado.",
            "input": "NE-OFFLINE",
            "ne_name": "NE-OFFLINE",
            "error": "Ne is not connected.",
        }
    ]


@pytest.mark.parametrize("error_status", [400, 401, 422, 502, 503, 504])
def test_http_failures_do_not_return_node_error_codes(error_status):
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with TestClient(app) as test_client:
            if error_status == 401:
                def reject_user():
                    raise HTTPException(status_code=401, detail="Unauthorized")

                app.dependency_overrides[require_user] = reject_user
                response = test_client.post(
                    "/mml/cell-summary-lte", json={"ne_names": ["NE-1"]}
                )
            elif error_status == 422:
                response = test_client.post("/mml/cell-summary-lte", json={})
            elif error_status == 503:
                with patch(
                    "app.api.routes.huawei.resolve_names",
                    new=AsyncMock(
                        side_effect=HTTPException(status_code=503, detail="Directory unavailable")
                    ),
                ):
                    response = test_client.post(
                        "/mml/cell-summary-lte", json={"ne_names": ["NE-1"]}
                    )
            else:
                with patch(
                    "app.api.routes.huawei._execute_mml",
                    new=AsyncMock(
                        side_effect=HTTPException(
                            status_code=error_status, detail="Upstream failure"
                        )
                    ),
                ):
                    response = test_client.post(
                        "/mml/cell-summary-lte", json={"ne_names": ["NE-1"]}
                    )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == error_status
    assert "errors" not in response.json()


@pytest.mark.parametrize(
    ("endpoint", "body", "target_column", "canonical_name", "command"),
    [
        (
            "/mml/cell-summary-umts",
            {"nodeb_name": "SITE-1"},
            "nodeb",
            "NODEB-1",
            'DSP UCELL:DSPT=BYNODEB,NODEBNAME="NODEB-1";',
        ),
        (
            "/mml/cell-summary-lte",
            {"ne_names": ["SITE-1"]},
            "nodo",
            "ENB-1",
            "DSP CELL:;",
        ),
        (
            "/mml/cell-summary-nr",
            {"ne_names": ["SITE-1"]},
            "nodo",
            "GNB-1",
            "DSP NRCELL:;",
        ),
    ],
)
def test_state_routes_resolve_using_technology_specific_directory_columns(
    endpoint, body, target_column, canonical_name, command
):
    input_name = body.get("nodeb_name") or body["ne_names"][0]
    resolution = {
        "input": input_name,
        "resolved": canonical_name,
        "status": "resolved",
    }
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=[resolution]),
            ) as resolve,
            patch(
                "app.api.routes.huawei._execute_mml",
                new=AsyncMock(return_value={"results": []}),
            ) as execute_mml,
            patch("app.api.routes.huawei._umts_rnc_names", return_value=_TEST_RNC_NAMES),
            TestClient(app) as test_client,
        ):
            response = test_client.post(endpoint, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["name_resolution"] == [resolution]
    resolve.assert_awaited_once_with([input_name], target_column)
    if target_column == "nodeb":
        execute_mml.assert_awaited_once_with(command, _TEST_RNC_NAMES)
        assert response.json()["nodeb_name"] == canonical_name
    else:
        execute_mml.assert_awaited_once_with(command, [canonical_name])


@pytest.mark.parametrize(
    ("endpoint", "body", "status_value", "target_column"),
    [
        ("/mml/cell-summary-umts", {"nodeb_name": "SITE-1"}, "missing_mapping", "nodeb"),
        ("/mml/cell-summary-lte", {"ne_names": ["SITE-1"]}, "ambiguous_mapping", "nodo"),
        ("/mml/cell-summary-nr", {"ne_names": ["SITE-1"]}, "missing_mapping", "nodo"),
    ],
)
def test_state_routes_classify_unusable_mappings_without_calling_huawei(
    endpoint, body, status_value, target_column
):
    input_name = body.get("nodeb_name") or body["ne_names"][0]
    resolution = {
        "input": input_name,
        "resolved": None,
        "status": status_value,
        "error": f"El sitio no tiene mapeo para {target_column}.",
    }
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(return_value=[resolution]),
            ),
            patch("app.api.routes.huawei._execute_mml", new=AsyncMock()) as execute_mml,
            TestClient(app) as test_client,
        ):
            response = test_client.post(endpoint, json=body)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    error = response.json()["errors"][0]
    assert error["code"] == "TECHNOLOGY_UNAVAILABLE"
    assert error["input"] == input_name
    assert error["ne_name"] is None
    execute_mml.assert_not_awaited()


@pytest.mark.parametrize(
    ("endpoint", "technology"),
    [("/mml/cell-summary-lte", "4G"), ("/mml/cell-summary-nr", "5G")],
)
def test_state_routes_classify_disconnected_and_empty_connected_nodes(endpoint, technology):
    for report, expected_code in [
        ({"error": "Ne is not connected."}, "NODE_DISCONNECTED"),
        ({"records": []}, "TECHNOLOGY_UNAVAILABLE"),
    ]:
        app.dependency_overrides[require_user] = lambda: "operator-1"
        try:
            with (
                patch(
                    "app.api.routes.huawei._execute_mml",
                    new=AsyncMock(
                        return_value={"results": [{"name": "NE-1", "report": report}]}
                    ),
                ),
                TestClient(app) as test_client,
            ):
                response = test_client.post(endpoint, json={"ne_names": ["NE-1"]})
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        body = response.json()
        assert body["records"] == []
        assert body["errors"][0]["code"] == expected_code
        assert body["errors"][0]["message"] == (
            "Nodo desconectado."
            if expected_code == "NODE_DISCONNECTED"
            else f"El nodo no tiene la tecnología {technology} disponible."
        )


@pytest.mark.parametrize(
    ("states", "expected_codes"),
    [
        (["Unavailable", "Unavailable"], ["NODE_DISCONNECTED"]),
        (["Unavailable", "Available"], []),
    ],
)
def test_umts_unavailable_cells_are_retained_and_only_all_unavailable_is_disconnected(
    states, expected_codes
):
    dsp_records = [
        {
            "Cell ID": str(index),
            "Cell name": f"NODEB-1_{index}",
            "Operation state": state,
        }
        for index, state in enumerate(states, start=1)
    ]
    lst_records = [
        {
            "Cell ID": str(index),
            "Max Transmit Power of Cell": "430",
            "Band Indicator": "BAND1",
            "Downlink UARFCN": "10787",
        }
        for index in range(1, len(states) + 1)
    ]
    execute_mml = AsyncMock(
        side_effect=[
            {"results": [{"name": "RNC-1", "report": {"records": dsp_records}}]},
            {"results": [{"name": "RNC-1", "report": {"records": lst_records}}]},
        ]
    )
    app.dependency_overrides[require_user] = lambda: "operator-1"
    try:
        with (
            patch(
                "app.api.routes.huawei.resolve_names",
                new=AsyncMock(
                    return_value=[
                        {"input": "SITE-1", "resolved": "NODEB-1", "status": "resolved"}
                    ]
                ),
            ),
            patch("app.api.routes.huawei._execute_mml", new=execute_mml),
            patch("app.api.routes.huawei._umts_rnc_names", return_value=["RNC-1"]),
            TestClient(app) as test_client,
        ):
            response = test_client.post(
                "/mml/cell-summary-umts", json={"nodeb_name": "SITE-1"}
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert len(body["records"]) == len(states)
    assert [error["code"] for error in body["errors"]] == expected_codes
