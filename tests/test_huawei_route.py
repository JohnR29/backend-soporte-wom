from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

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
        {"ne_name": name, "error": "NodeB is not configured"}
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
        "errors": [{"ne_name": name, "error": "NodeB is not configured"} for name in [
            "STG03", "STG04", "STG05", "STG06", "ATF02", "CCP2", "PTM01",
        ]],
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
    assert body["alarms"][0]["cleared"] == "9"
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
        ]
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
        ]
    }
    assert client.get.await_count == 2
    client.get.assert_awaited_with(
        "/api/rest/performanceManagement/v2/measurementResults/1",
        headers={"X-Auth-Token": "test-token"},
        params={"limit": 1000},
    )

