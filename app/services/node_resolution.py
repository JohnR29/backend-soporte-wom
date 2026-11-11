import logging
from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher

import numpy as np
from fastapi import HTTPException
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

logger = logging.getLogger(__name__)

_TARGET_COLUMNS = {"nodo", "nodeb"}
_engine: AsyncEngine | None = None


def init_site_directory(database_url: str | None) -> None:
    global _engine
    _engine = None
    if not database_url:
        logger.info("Site directory disabled: SITE_DIRECTORY_DATABASE_URL is not set")
        return
    try:
        _engine = create_async_engine(database_url, pool_pre_ping=True)
    except SQLAlchemyError:
        logger.exception("Could not initialize the site-directory engine")


async def close_site_directory() -> None:
    global _engine
    engine = _engine
    _engine = None
    if engine is not None:
        await engine.dispose()


def _normalize(value: str | None) -> str:
    return (value or "").strip().casefold()


def _build_suggestion_index(sites: Sequence[str]) -> dict:
    candidates = sorted(sites, key=lambda site: (_normalize(site), site))
    if not candidates:
        return {
            "candidates": [],
            "normalized_candidates": [],
            "char_indexes": {},
            "char_counts": np.zeros((0, 0), dtype=np.uint8),
            "lengths": np.array([], dtype=np.float64),
            "matchers": {},
        }

    normalized_candidates = [_normalize(site) for site in candidates]
    alphabet = sorted(set("".join(normalized_candidates)))
    char_indexes = {char: index for index, char in enumerate(alphabet)}
    char_counts = np.zeros((len(candidates), len(alphabet)), dtype=np.uint8)
    for row_index, candidate in enumerate(normalized_candidates):
        for char, count in Counter(candidate).items():
            char_counts[row_index, char_indexes[char]] = count
    lengths = np.fromiter((len(candidate) for candidate in normalized_candidates), dtype=np.float64)
    return {
        "candidates": candidates,
        "normalized_candidates": normalized_candidates,
        "char_indexes": char_indexes,
        "char_counts": char_counts,
        "lengths": lengths,
        "matchers": {},
    }


def _rank_suggestions(name: str, suggestion_index: dict) -> list[tuple[str, float]]:
    candidates = suggestion_index["candidates"]
    if not candidates:
        return []
    normalized_candidates = suggestion_index["normalized_candidates"]
    char_indexes = suggestion_index["char_indexes"]
    char_counts = suggestion_index["char_counts"]
    lengths = suggestion_index["lengths"]
    normalized_name = _normalize(name)
    name_counts = Counter(normalized_name)
    overlap = np.zeros(len(candidates), dtype=np.uint16)
    for char, count in name_counts.items():
        char_index = char_indexes.get(char)
        if char_index is not None:
            overlap += np.minimum(char_counts[:, char_index], count)

    denominators = len(normalized_name) + lengths
    upper_bounds = np.divide(
        2 * overlap,
        denominators,
        out=np.ones(len(candidates), dtype=np.float64),
        where=denominators != 0,
    )
    candidate_order = np.argsort(-upper_bounds, kind="stable")
    best: list[tuple[float, str, str]] = []
    matchers = suggestion_index["matchers"]
    for index in candidate_order:
        upper_bound = upper_bounds[index]
        if len(best) == 5 and upper_bound < best[-1][0]:
            break
        candidate = normalized_candidates[index]
        matcher = matchers.get(index)
        if matcher is None:
            matcher = SequenceMatcher(None, normalized_name, candidate)
            matchers[index] = matcher
        else:
            matcher.set_seq1(normalized_name)
        score = matcher.ratio()
        best.append((score, _normalize(candidates[index]), candidates[index]))
        best.sort(key=lambda item: (-item[0], item[1], item[2]))
        del best[5:]
    return [(site, score) for score, _, site in best if score >= 0.6]


async def resolve_names(
    names: Sequence[str],
    target_column: str,
    *,
    detailed_suggestions: bool = False,
) -> list[dict]:
    if target_column not in _TARGET_COLUMNS:
        raise ValueError(f"Unsupported site-directory target column: {target_column}")
    if _engine is None:
        raise HTTPException(
            status_code=503,
            detail="El directorio de sitios no está configurado o disponible.",
        )

    normalized_names = list(dict.fromkeys(_normalize(name) for name in names))
    query = text(
        "SELECT sitio, nodo, nodeb FROM public.cellreference "
        "WHERE lower(btrim(sitio)) IN :names "
        f"OR lower(btrim({target_column})) IN :names"
    ).bindparams(bindparam("names", expanding=True))
    suggestions_query = text(
        "SELECT sitio, nodo, nodeb FROM public.cellreference WHERE sitio IS NOT NULL"
    )

    try:
        async with _engine.connect() as connection:
            result = await connection.execute(query, {"names": normalized_names})
            rows = result.mappings().all()
            sites_by_name: dict[str, list[dict]] = {}
            targets_by_name: dict[str, dict] = {}
            for row in rows:
                normalized_site = _normalize(row["sitio"])
                if normalized_site:
                    sites_by_name.setdefault(normalized_site, []).append(row)
                normalized_target = _normalize(row[target_column])
                if normalized_target:
                    targets_by_name.setdefault(normalized_target, row)
            misses = {
                _normalize(name)
                for name in names
                if _normalize(name) not in sites_by_name
                and _normalize(name) not in targets_by_name
            }
            site_rows = []
            if misses:
                suggestions_result = await connection.execute(suggestions_query)
                site_rows = suggestions_result.mappings().all()
    except SQLAlchemyError as error:
        logger.exception("Could not query the site directory")
        raise HTTPException(
            status_code=503,
            detail="El directorio de sitios no está configurado o disponible.",
        ) from error

    unique_sites: dict[str, dict] = {}
    for row in site_rows:
        normalized_site = _normalize(row["sitio"])
        if normalized_site:
            unique_sites.setdefault(normalized_site, dict(row))
    sites = [row["sitio"] for row in unique_sites.values()]
    suggestion_index = _build_suggestion_index(sites) if misses else None
    resolutions = []
    for name in names:
        normalized_name = _normalize(name)
        site_matches = sites_by_name.get(normalized_name, [])
        if not site_matches and normalized_name not in targets_by_name:
            ranked_suggestions = _rank_suggestions(name, suggestion_index)
            suggestions = [
                {
                    "nemonica": unique_sites[_normalize(site)]["sitio"],
                    "nodo": unique_sites[_normalize(site)]["nodo"],
                    "nodeb": unique_sites[_normalize(site)]["nodeb"],
                    "similarity": score,
                }
                for site, score in ranked_suggestions
            ]
            resolutions.append(
                {
                    "input": name,
                    "resolved": None,
                    "status": "not_found",
                    "error": "No se encontró el sitio.",
                    "suggestions": (
                        suggestions
                        if detailed_suggestions
                        else [suggestion["nemonica"] for suggestion in suggestions]
                    ),
                }
            )
            continue

        if site_matches:
            resolved_site = min(str(row["sitio"]) for row in site_matches)
            target_values: dict[str, set[str]] = {}
            for row in site_matches:
                value = row[target_column]
                if value and str(value).strip():
                    target_values.setdefault(_normalize(value), set()).add(value)
            if len(target_values) > 1:
                resolutions.append(
                    {
                        "input": name,
                        "resolved": None,
                        "resolved_site": resolved_site,
                        "status": "ambiguous_mapping",
                        "error": f"El sitio tiene múltiples mapeos para {target_column}.",
                        "suggestions": [],
                    }
                )
                continue
            canonical_target = min(next(iter(target_values.values()))) if target_values else None
        else:
            resolved_row = targets_by_name[normalized_name]
            resolved_site = str(resolved_row["sitio"])
            canonical_target = resolved_row[target_column]

        if not canonical_target or not str(canonical_target).strip():
            resolutions.append(
                {
                    "input": name,
                    "resolved": None,
                    "resolved_site": resolved_site,
                    "status": "missing_mapping",
                    "error": f"El sitio no tiene mapeo para {target_column}.",
                    "suggestions": [],
                    "available_technologies": [
                        technology
                        for technology, column in (("3G", "nodeb"), ("4G", "nodo"), ("5G", "nodo"))
                        if any(row[column] and str(row[column]).strip() for row in site_matches)
                    ],
                }
            )
        else:
            resolutions.append(
                {
                    "input": name,
                    "resolved": canonical_target,
                    "resolved_site": resolved_site,
                    "status": "resolved",
                }
            )
    return resolutions


async def resolve_alarm_name(site_name: str, technology: str) -> dict:
    target_column = "nodeb" if technology == "3G" else "nodo"
    return (
        await resolve_names(
            [site_name],
            target_column,
            detailed_suggestions=True,
        )
    )[0]