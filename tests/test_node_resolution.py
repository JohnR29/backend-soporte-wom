import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services.node_resolution import resolve_names


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        if "lower(btrim(sitio)) IN" not in sql:
            return FakeResult([row for row in self.rows if row["sitio"]])
        target_column = "nodeb" if "lower(btrim(nodeb))" in sql else "nodo"
        names = set(parameters["names"])
        matches = [
            row
            for row in self.rows
            if (row["sitio"] or "").strip().casefold() in names
            or (row[target_column] or "").strip().casefold() in names
        ]
        return FakeResult(matches)


class FakeEngine:
    def __init__(self, rows):
        self.rows = rows

    def connect(self):
        return FakeConnection(self.rows)


@pytest.fixture
def directory_engine(monkeypatch):
    from app.services import node_resolution

    engine = FakeEngine(
        [
            {"sitio": "AN0069", "nodo": "MBTS-AN0069", "nodeb": "UAN0069"},
            {"sitio": "AN0070", "nodo": None, "nodeb": "UAN0070"},
        ]
    )
    monkeypatch.setattr(node_resolution, "_engine", engine)
    return engine


def test_resolve_site_uses_trimmed_case_insensitive_exact_match(directory_engine):
    result = asyncio.run(resolve_names(["  an0069  "], "nodo"))

    assert result == [
        {"input": "  an0069  ", "resolved": "MBTS-AN0069", "status": "resolved"}
    ]


def test_resolve_direct_full_node_to_canonical_directory_value(directory_engine):
    result = asyncio.run(resolve_names([" mbts-an0069 "], "nodo"))

    assert result == [
        {"input": " mbts-an0069 ", "resolved": "MBTS-AN0069", "status": "resolved"}
    ]


def test_resolve_site_without_target_mapping(directory_engine):
    result = asyncio.run(resolve_names(["AN0070"], "nodo"))

    assert result[0]["input"] == "AN0070"
    assert result[0]["resolved"] is None
    assert result[0]["status"] == "missing_mapping"


def test_resolve_reports_ambiguous_target_mapping(monkeypatch):
    from app.services import node_resolution

    monkeypatch.setattr(
        node_resolution,
        "_engine",
        FakeEngine(
            [
                {"sitio": "RM173", "nodo": "MBTS-RM173-2", "nodeb": "RM173-2"},
                {"sitio": "RM173", "nodo": "MBTS-RM173-3", "nodeb": "RM173-3"},
            ]
        ),
    )

    result = asyncio.run(resolve_names(["RM173"], "nodo"))[0]

    assert result == {
        "input": "RM173",
        "resolved": None,
        "status": "ambiguous_mapping",
        "error": "El sitio tiene múltiples mapeos para nodo.",
    }


def test_resolve_reports_service_unavailable_without_engine(monkeypatch):
    from app.services import node_resolution

    monkeypatch.setattr(node_resolution, "_engine", None)

    with pytest.raises(HTTPException) as error:
        asyncio.run(resolve_names(["AN0069"], "nodo"))

    assert error.value.status_code == 503


def test_suggestions_rank_by_similarity_then_case_insensitive_name(monkeypatch):
    from app.services import node_resolution

    engine = FakeEngine(
        [
            {"sitio": "AA2", "nodo": "N-2", "nodeb": None},
            {"sitio": "aa1", "nodo": "N-1", "nodeb": None},
            {"sitio": "AX0", "nodo": "N-3", "nodeb": None},
            {"sitio": "AA0X", "nodo": "N-5", "nodeb": None},
            {"sitio": "ZZZ", "nodo": "N-4", "nodeb": None},
        ]
    )
    monkeypatch.setattr(node_resolution, "_engine", engine)

    result = asyncio.run(resolve_names(["AA0"], "nodo"))[0]

    assert result["status"] == "not_found"
    assert result["suggestions"][:4] == ["AA0X", "aa1", "AA2", "AX0"]


def test_suggestions_are_limited_to_five_and_empty_when_directory_has_no_sites(monkeypatch):
    from app.services import node_resolution

    sites = [f"SITE{index}" for index in range(7)]
    monkeypatch.setattr(
        node_resolution,
        "_engine",
        FakeEngine(
            [{"sitio": site, "nodo": f"N-{site}", "nodeb": None} for site in sites]
        ),
    )
    suggestions = asyncio.run(resolve_names(["MISS"], "nodo"))[0]["suggestions"]
    assert len(suggestions) == 5

    monkeypatch.setattr(node_resolution, "_engine", FakeEngine([]))
    empty_suggestions = asyncio.run(resolve_names(["MISS"], "nodo"))[0]["suggestions"]
    assert empty_suggestions == []


def test_versioned_typo_cases_meet_top_five_recall(monkeypatch):
    from app.services import node_resolution

    fixture_path = Path(__file__).parent / "fixtures" / "node_resolution_typo_cases.json"
    typo_cases = json.loads(fixture_path.read_text(encoding="utf-8"))["cases"]
    sites = sorted({case["expected"] for case in typo_cases})
    monkeypatch.setattr(
        node_resolution,
        "_engine",
        FakeEngine(
            [{"sitio": site, "nodo": f"N-{site}", "nodeb": None} for site in sites]
        ),
    )

    hits = 0
    for case in typo_cases:
        result = asyncio.run(resolve_names([case["input"]], "nodo"))[0]
        hits += case["expected"] in result["suggestions"]

    assert hits / len(typo_cases) >= 0.9