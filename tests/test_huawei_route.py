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
    assert body["errors"] == [{"ne_name": "NE-OFFLINE", "error": "Ne is not connected."}]


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
    records = response.json()["records"]
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
