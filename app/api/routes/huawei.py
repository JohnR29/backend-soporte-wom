from fastapi import APIRouter, Depends, HTTPException, status
import httpx
import pandas as pd
from pydantic import BaseModel, Field
import logging

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


async def _execute_mml(command: str, ne_names: list[str]) -> dict:
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
    for result in payload.get("results", []):
        if isinstance(result.get("report"), str):
            try:
                parsed_report = MMLAutoParser.parse(result["report"])
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
    }
