from fastapi import APIRouter, Depends, HTTPException, status
import httpx
import pandas as pd
from pydantic import BaseModel, Field
import logging
import re

from app.api.routes.auth import require_user
from app.services.huawei_client import get_client, get_huawei_headers, mark_huawei_activity
from app.services.mml_parser import MMLAutoParser

router = APIRouter(tags=["mml"])
logger = logging.getLogger(__name__)


class MmlCommandRequest(BaseModel):
    command: str = Field(min_length=1)
    ne_names: list[str] = Field(min_length=1, max_length=100)


class CellSummaryRequest(BaseModel):
    ne_names: list[str] = Field(min_length=1, max_length=100)


_MML_SUCCESS_RET_CODE = "90000"
_NE_NOT_EXIST_PATTERN = re.compile(r"is not exist:\s*(.+)$", re.IGNORECASE)


class _MissingNeError(Exception):
    """Huawei rejected the whole batch because it contains unknown NE names."""

    def __init__(self, missing_names: list[str]):
        self.missing_names = missing_names


def _extract_missing_ne_names(ret_message: str | None) -> list[str]:
    match = _NE_NOT_EXIST_PATTERN.search(ret_message or "")
    if not match:
        return []
    return [name.strip() for name in match.group(1).rstrip(".").split(",") if name.strip()]


def _missing_ne_result(name: str) -> dict:
    return {
        "name": name,
        "report": {"error": "NE no existe o el nombre está mal escrito."},
        "result": "Failed.",
        "retCode": -1,
        "serialId": None,
    }


def _result_failed(result: dict) -> bool:
    """A per-NE result is a failure if its own retCode/result flag says so."""
    ret_code = result.get("retCode")
    if ret_code not in (0, "0", None):
        return True
    return str(result.get("result", "")).strip().lower().startswith("fail")


async def _post_mml(command: str, ne_names: list[str]) -> dict:
    """Post a single MML command to Huawei and return its raw JSON payload.

    Raises _MissingNeError when Huawei rejects the whole batch for containing
    unknown NE names, so the caller can retry without them.
    """
    client = get_client()
    try:
        logger.info("Ejecutando MML: %s", command)
        response = await client.post(
            "/api/rest/mmlManagement/v1/command",
            headers=await get_huawei_headers(),
            json={"command": command, "neNames": ne_names},
        )
        response.raise_for_status()
        mark_huawei_activity()
    except httpx.HTTPStatusError as error:
        try:
            error_payload = error.response.json()
        except ValueError:
            error_payload = None
        missing_names = (
            _extract_missing_ne_names(error_payload.get("retMessage"))
            if isinstance(error_payload, dict)
            else []
        )
        if missing_names:
            raise _MissingNeError(missing_names) from error
        if isinstance(error_payload, dict) and error_payload.get("retMessage"):
            # Huawei can reject the whole batch with an HTTP error status but
            # still carry its retCode/retMessage envelope.
            logger.error(
                "Huawei MML request rejected: HTTP %s retCode=%s retMessage=%s",
                error.response.status_code,
                error_payload.get("retCode"),
                error_payload.get("retMessage"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_payload["retMessage"],
            ) from error
        logger.exception("Huawei MML request returned an HTTP error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei MML request failed",
        ) from error
    except httpx.ProxyError as error:
        logger.exception("Huawei MML request blocked by proxy: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei MML request blocked by proxy (check proxy ACL for the Huawei host)",
        ) from error
    except httpx.HTTPError as error:
        logger.exception("Huawei MML request could not be completed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei MML request could not be completed",
        ) from error

    payload = response.json()

    # Some failures (e.g. unknown NE names) never reach the per-NE "results" stage.
    if str(payload.get("retCode")) not in (_MML_SUCCESS_RET_CODE, "0") and "results" not in payload:
        missing_names = _extract_missing_ne_names(payload.get("retMessage"))
        if missing_names:
            raise _MissingNeError(missing_names)
        logger.error(
            "Huawei MML request rejected: retCode=%s retMessage=%s",
            payload.get("retCode"),
            payload.get("retMessage"),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=payload.get("retMessage", "Huawei MML request rejected"),
        )

    return payload


async def _execute_mml(command: str, ne_names: list[str]) -> dict:
    remaining = list(ne_names)
    missing_results: list[dict] = []
    payload: dict = {"results": []}

    while remaining:
        try:
            payload = await _post_mml(command, remaining)
            break
        except _MissingNeError as error:
            newly_missing = [name for name in error.missing_names if name in remaining]
            if not newly_missing:
                # Avoid an infinite loop if Huawei reports names we don't recognize.
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"The following NE list is not exist: {', '.join(error.missing_names)}.",
                ) from error
            missing_results.extend(_missing_ne_result(name) for name in newly_missing)
            remaining = [name for name in remaining if name not in newly_missing]

    if missing_results:
        results_by_name = {result["name"]: result for result in missing_results}
        for result in payload.get("results", []):
            results_by_name[result.get("name")] = result
        payload["results"] = [results_by_name[name] for name in ne_names if name in results_by_name]

    for result in payload.get("results", []):
        report = result.get("report")
        if not isinstance(report, str):
            continue
        if _result_failed(result):
            # Failed NEs return a plain-text reason (e.g. "Ne is not connected."), not an MML report.
            result["report"] = {"error": report}
            continue
        try:
            parsed_report = MMLAutoParser.parse(report)
            result["report"] = {
                "retCode": parsed_report["retCode"],
                "timestamp": parsed_report["timestamp"],
                "records": parsed_report["records"],
            }
        except ValueError as error:
            result["report"] = {
                "error": str(error),
            }

    return payload


@router.post("/mml/command")
async def execute_mml_command(
    request: MmlCommandRequest,
    user_id: str = Depends(require_user),
):
    """Execute one synchronous MML command against up to 100 network elements."""
    return await _execute_mml(request.command, request.ne_names)


def _records_dataframe(
    payload: dict,
    command_name: str,
    key_column: str = "Local Cell ID",
) -> pd.DataFrame:
    records: list[dict] = []
    for result in payload.get("results", []):
        report = result.get("report")
        if not isinstance(report, dict) or "error" in report:
            continue
        for record in report.get("records", []):
            if isinstance(record, dict):
                records.append({**record, "ne_name": result.get("name")})

    dataframe = pd.DataFrame.from_records(records)
    if key_column not in dataframe.columns:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Huawei {command_name} response has no '{key_column}' column",
        )
    return dataframe


def _ne_errors(*payloads: dict) -> list[dict]:
    """Collect NE-level failures (offline/unknown NEs) so they aren't silently dropped."""
    errors: dict[str, str] = {}
    for payload in payloads:
        for result in payload.get("results", []):
            report = result.get("report")
            if isinstance(report, dict) and "error" in report:
                errors.setdefault(result.get("name"), report["error"])
    return [{"ne_name": name, "error": error} for name, error in errors.items()]


@router.post("/mml/cell-summary-lte")
async def create_cell_summary(
    request: CellSummaryRequest,
    user_id: str = Depends(require_user),
):
    """Extrae el estado de celdas LTE en tiempo real"""
    dsp_payload = await _execute_mml("DSP CELL:;", request.ne_names)
    dsp_dataframe = _records_dataframe(dsp_payload, "DSP CELL")[[
        "ne_name",
        "Local Cell ID",
        "Cell Name",
        "Cell instance state",
        "Maximum transmit power(0.1dBm)",
    ]]

    lst_payload = await _execute_mml("LST CELL:;", request.ne_names)
    lst_dataframe = _records_dataframe(lst_payload, "LST CELL")[[
        "ne_name",
        "Local Cell ID",
        "Frequency band",
        "Downlink EARFCN",
    ]]

    summary_dataframe = dsp_dataframe.merge(
        lst_dataframe,
        on=["ne_name", "Local Cell ID"],
        how="left",
        validate="one_to_one",
    )
    summary_dataframe = summary_dataframe.astype(object).where(summary_dataframe.notna(), None)

    return {
        "commands": ["DSP CELL:;", "LST CELL:;"],
        "records": summary_dataframe.to_dict(orient="records"),
        "count": len(summary_dataframe),
        "errors": _ne_errors(dsp_payload, lst_payload),
    }


@router.post("/mml/cell-summary-nr")
async def create_cell_summary_nr(
    request: CellSummaryRequest,
    user_id: str = Depends(require_user),
):
    """Extrae el estado y la configuración de celdas NR en tiempo real."""
    nrcell_payload = await _execute_mml("DSP NRCELL:;", request.ne_names)
    nrcell_dataframe = _records_dataframe(
        nrcell_payload,
        "DSP NRCELL",
        key_column="NR Cell ID",
    )[[
        "ne_name",
        "NR Cell ID",
        "Cell Name",
        "Cell Available State",
    ]]

    nrducell_payload = await _execute_mml("LST NRDUCELL:;", request.ne_names)
    nrducell_dataframe = _records_dataframe(
        nrducell_payload,
        "LST NRDUCELL",
        key_column="Cell ID",
    )[[
        "ne_name",
        "Cell ID",
        "Frequency Band",
        "Downlink NARFCN",
    ]].rename(columns={"Cell ID": "NR Cell ID"})

    summary_dataframe = nrcell_dataframe.merge(
        nrducell_dataframe,
        on=["ne_name", "NR Cell ID"],
        how="left",
        validate="many_to_one",
    )

    nrducelltrp_payload = await _execute_mml("LST NRDUCELLTRP:;", request.ne_names)
    nrducelltrp_dataframe = _records_dataframe(
        nrducelltrp_payload,
        "LST NRDUCELLTRP",
        key_column="NR DU Cell ID",
    )[[
        "ne_name",
        "NR DU Cell ID",
        "Max Transmit Power(0.1dBm)",
    ]]

    summary_dataframe = summary_dataframe.merge(
        nrducelltrp_dataframe,
        left_on=["ne_name", "NR Cell ID"],
        right_on=["ne_name", "NR DU Cell ID"],
        how="left",
        validate="many_to_one",
    ).drop(columns="NR DU Cell ID")
    summary_dataframe = summary_dataframe.astype(object).where(summary_dataframe.notna(), None)

    return {
        "commands": ["DSP NRCELL:;", "LST NRDUCELL:;", "LST NRDUCELLTRP:;"],
        "records": summary_dataframe.to_dict(orient="records"),
        "count": len(summary_dataframe),
        "errors": _ne_errors(nrcell_payload, nrducell_payload, nrducelltrp_payload),
    }
