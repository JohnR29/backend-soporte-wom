from app.services.mml_parser import MMLAutoParser


HORIZONTAL_REPORT = """+++ NE-001 2026-08-23 10:20:30
RETCODE = 0
---
CELL  STATUS  COUNT

cell-a  ACTIVE  3
cell-b  NULL  0
(Number of results = 2)
---    END"""

VERTICAL_REPORT = """+++ NE-002 2026-08-23 11:20:30
RETCODE = 0
---
NAME = cell-a
VALUE = first
 = second

NAME = cell-b
VALUE = NULL
---    END"""


def test_parse_horizontal_report():
    parsed = MMLAutoParser.parse(HORIZONTAL_REPORT)

    assert parsed == {
        "neName": "NE-001",
        "formatDetected": "horizontal",
        "retCode": 0,
        "timestamp": "2026-08-23 10:20:30",
        "records": [
            {"CELL": "cell-a", "STATUS": "ACTIVE", "COUNT": "3"},
            {"CELL": "cell-b", "STATUS": None, "COUNT": "0"},
        ],
    }


def test_parse_vertical_report_flattens_multivalue_attributes():
    parsed = MMLAutoParser.parse(VERTICAL_REPORT)

    assert parsed["formatDetected"] == "vertical"
    assert parsed["records"] == [
        {"NAME": "cell-a", "VALUE": "first, second"},
        {"NAME": "cell-b", "VALUE": None},
    ]


def test_parse_vertical_report_can_preserve_lists():
    parsed = MMLAutoParser.parse(VERTICAL_REPORT, flatten_lists=False)

    assert parsed["records"][0]["VALUE"] == ["first", "second"]


def test_parse_nonzero_retcode_returns_no_records():
    report = VERTICAL_REPORT.replace("RETCODE = 0", "RETCODE = 5")

    assert MMLAutoParser.parse(report) == {
        "neName": "NE-002",
        "formatDetected": "unknown",
        "retCode": 5,
        "timestamp": "2026-08-23 11:20:30",
        "records": [],
    }


def test_parse_incomplete_report_raises_value_error():
    incomplete_report = HORIZONTAL_REPORT.replace("---    END", "")

    try:
        MMLAutoParser.parse(incomplete_report)
    except ValueError as error:
        assert "Reporte MML incompleto" in str(error)
    else:
        raise AssertionError("Expected an incomplete MML report to raise ValueError")
