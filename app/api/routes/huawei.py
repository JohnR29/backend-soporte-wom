from fastapi import APIRouter, Depends, HTTPException, status
import httpx
import pandas as pd
from pydantic import BaseModel, Field
from asyncio import sleep as asyncio_sleep
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.api.routes.auth import require_user
from app.core.config import get_settings
from app.services.huawei_client import get_client, get_huawei_headers, mark_huawei_activity
from app.services.mml_parser import MMLAutoParser

router = APIRouter(tags=["MML"])
logger = logging.getLogger(__name__)


class MmlCommandRequest(BaseModel):
    command: str = Field(
        min_length=1,
        description="Comando MML completo que se ejecutará en cada nodo.",
        examples=["display version;"],
    )
    ne_names: list[str] = Field(
        min_length=1,
        max_length=100,
        description="Nombres de los nodos que recibirán el comando (entre 1 y 100).",
        examples=[["NE-001", "NE-002"]],
    )


class CellSummaryRequest(BaseModel):
    ne_names: list[str] = Field(
        min_length=1,
        max_length=100,
        description="Nombres de los nodos que se consultarán (entre 1 y 100).",
        examples=[["NE-001", "NE-002"]],
    )


class UmtsCellSummaryRequest(BaseModel):
    nodeb_name: str = Field(
        min_length=1,
        description="Nombre del NodeB a buscar en la lista fija de RNC.",
        examples=["URM3644"],
    )


class MeasurementResultsRequest(BaseModel):
    ne_names: list[str] = Field(
        min_length=1,
        max_length=100,
        description="Nombres de los eNodeB a consultar (entre 1 y 100).",
        examples=[["MBTS-RM3644"]],
    )


_MML_SUCCESS_RET_CODE = "90000"
_NE_NOT_EXIST_PATTERN = re.compile(r"is not exist:\s*(.+)$", re.IGNORECASE)
_MML_RESPONSES = {
    400: {"description": "Solicitud inválida o nodo inexistente."},
    401: {"description": "Falta el token o no es válido."},
    422: {"description": "Los datos enviados no cumplen el formato requerido."},
    502: {"description": "No fue posible completar la comunicación con Huawei."},
}


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


# Fixed performance-query parameters (see .github/skills/huawei-api/references/endpoints.md).
_PM_TIME_FORMAT = "utcTimeString"
_PM_PERIOD_MINUTES = 60
_PM_COUNTER_IDS = [1543503856, 1543503857, 1543503836, 1543503845]
# KPI name for each id above, same order (translated from Huawei's counter catalog).
_PM_COUNTER_NAMES = ["ERAB Success Rate", "User Max", "Traffic", "Throughput"]
_PM_NE_TYPE_NAME = "eNodeB"
_PM_RUNNING_RET_CODE = "90037"
_PM_AVAILABILITY_LAG_MINUTES = 15  # Huawei publishes an hourly bucket ~15 min after it closes.
_PM_POLL_INTERVAL_SECONDS = 3
_PM_POLL_TIMEOUT_SECONDS = 120
_PM_RESULT_LIMIT = 1000
_CHILE_TZ = ZoneInfo("America/Santiago")


def _last_24h_window() -> tuple[str, str]:
    """Last 24h ending at the latest hourly bucket Huawei has already published."""
    now = datetime.now(timezone.utc)
    hour_floor = now.replace(minute=0, second=0, microsecond=0)
    if now >= hour_floor + timedelta(minutes=_PM_AVAILABILITY_LAG_MINUTES):
        end_time = hour_floor
    else:
        end_time = hour_floor - timedelta(hours=1)
    start_time = end_time - timedelta(hours=24)
    time_format = "%Y-%m-%dT%H:%M:%SZ"
    return start_time.strftime(time_format), end_time.strftime(time_format)


def _utc_string_to_chile_time(value: str | None) -> str | None:
    """Huawei reports startTime in UTC; display it in Chile local time to avoid confusion."""
    if not value:
        return value
    try:
        utc_dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return value
    return utc_dt.astimezone(_CHILE_TZ).strftime("%Y-%m-%dT%H:%M:%S")


def _raise_for_huawei_error(error: httpx.HTTPStatusError, action: str) -> None:
    try:
        error_payload = error.response.json()
    except ValueError:
        error_payload = None
    if isinstance(error_payload, dict) and error_payload.get("retMessage"):
        logger.error(
            "Huawei %s request rejected: HTTP %s retCode=%s retMessage=%s",
            action,
            error.response.status_code,
            error_payload.get("retCode"),
            error_payload.get("retMessage"),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_payload["retMessage"],
        ) from error
    logger.exception("Huawei %s request returned an HTTP error: %s", action, error)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Huawei {action} request failed",
    ) from error


async def _poll_measurement_results(task_id: str) -> list[dict]:
    """Fetch every page of an async measurement task, retrying while it's still running."""
    client = get_client()
    deadline = time.monotonic() + _PM_POLL_TIMEOUT_SECONDS
    merged_results: list = []
    marker: str | None = None

    while True:
        params: dict = {"limit": _PM_RESULT_LIMIT}
        if marker:
            params["marker"] = marker
        try:
            response = await client.get(
                f"/api/rest/performanceManagement/v2/measurementResults/{task_id}",
                headers=await get_huawei_headers(),
                params=params,
            )
            response.raise_for_status()
            mark_huawei_activity()
        except httpx.HTTPStatusError as error:
            _raise_for_huawei_error(error, "performance query fetch")
        except httpx.ProxyError as error:
            logger.exception("Huawei performance query fetch blocked by proxy: %s", error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Huawei performance query blocked by proxy (check proxy ACL for the Huawei host)",
            ) from error
        except httpx.HTTPError as error:
            logger.exception("Huawei performance query fetch could not be completed: %s", error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Huawei performance query fetch could not be completed",
            ) from error

        payload = response.json()

        if str(payload.get("retCode")) == _PM_RUNNING_RET_CODE:
            if time.monotonic() >= deadline:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Huawei performance query timed out while processing",
                )
            await asyncio_sleep(_PM_POLL_INTERVAL_SECONDS)
            continue

        merged_results.extend(payload.get("result", []))
        marker = payload.get("marker")
        if not marker or marker == "null":
            break
        if time.monotonic() >= deadline:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Huawei performance query timed out while paginating",
            )

    return merged_results


def _flatten_measurement_results(result_items: list[dict]) -> dict:
    """Turn Huawei's counterValues/objectName shape into flat, dataframe-ready records."""
    records = []
    for item in result_items:
        object_name = item.get("objectName") or {}
        counter_values = item.get("counterValues") or []
        record = {
            "startTime": _utc_string_to_chile_time(item.get("startTime")),
            "neName": item.get("neName"),
            "Cell Name": object_name.get("Cell Name"),
            "Local Cell ID": object_name.get("Local Cell ID"),
        }
        record.update(zip(_PM_COUNTER_NAMES, counter_values))
        records.append(record)
    return {"records": records}


async def _create_measurement_task(ne_names: list[str]) -> dict:
    """Create a Huawei performance query for the last available 24h and return its results."""
    start_time, end_time = _last_24h_window()
    client = get_client()
    body = {
        "timeFormat": _PM_TIME_FORMAT,
        "startTime": start_time,
        "endTime": end_time,
        "period": _PM_PERIOD_MINUTES,
        "counterIds": _PM_COUNTER_IDS,
        "isQueryAllNe": 0,
        "neTypeName": _PM_NE_TYPE_NAME,
        "neNames": ne_names,
    }
    try:
        response = await client.post(
            "/api/rest/performanceManagement/v2/measurementResults",
            headers=await get_huawei_headers(),
            json=body,
        )
        response.raise_for_status()
        mark_huawei_activity()
    except httpx.HTTPStatusError as error:
        _raise_for_huawei_error(error, "performance query")
    except httpx.ProxyError as error:
        logger.exception("Huawei performance query blocked by proxy: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei performance query blocked by proxy (check proxy ACL for the Huawei host)",
        ) from error
    except httpx.HTTPError as error:
        logger.exception("Huawei performance query could not be completed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei performance query could not be completed",
        ) from error

    payload = response.json()
    if response.status_code == status.HTTP_202_ACCEPTED or str(payload.get("retCode")) == _PM_RUNNING_RET_CODE:
        result_items = await _poll_measurement_results(payload["taskId"])
    else:
        result_items = payload.get("result", [])
    return _flatten_measurement_results(result_items)


@router.post(
    "/mml/kpis",
    summary="Consultar KPIs de performance (últimas 24h)",
    description=(
        "Consulta contadores de performance fijos para los eNodeB indicados, "
        "en la ventana de 24h más reciente ya publicada por Huawei (hay un "
        "desfase de ~15 min por hora). Si Huawei procesa la consulta de forma "
        "asíncrona, se hace polling automático hasta consolidar el resultado. "
        "La respuesta viene aplanada (una fila por celda/hora) para poder "
        "convertirla directamente a un DataFrame."
    ),
    response_description="Registros aplanados con un KPI por columna (records[]).",
    responses=_MML_RESPONSES,
)
async def get_measurement_kpis(
    request: MeasurementResultsRequest,
    user_id: str = Depends(require_user),
) -> dict:
    return await _create_measurement_task(request.ne_names)


@router.post(
    "/mml/command",
    summary="Ejecutar comando MML",
    description=(
        "Ejecuta un comando MML en un lote de nodos Huawei. Los nodos "
        "operativos devuelven su reporte parseado; los nodos desconectados "
        "o inexistentes se conservan en `results` con su mensaje de error. "
        "Si Huawei rechaza el lote por un nodo inexistente, se reintenta con "
        "los nodos restantes."
    ),
    response_description="Resultado individual de cada nodo solicitado.",
    responses=_MML_RESPONSES,
)
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


def _umts_rnc_names() -> list[str]:
    """Fixed RNC list to probe for a NodeB (Huawei has no endpoint to enumerate RNCs)."""
    return [name.strip() for name in get_settings().umts_rnc_names.split(",") if name.strip()]


def _successful_ne_names(payload: dict) -> list[str]:
    """NE names whose report was parsed successfully (no 'error' key)."""
    return [
        result.get("name")
        for result in payload.get("results", [])
        if isinstance(result.get("report"), dict) and "error" not in result["report"]
    ]


def _umts_ne_errors(*payloads: dict) -> list[dict]:
    """Like _ne_errors but surfaces Huawei's plain-text 'result' (e.g. 'NodeB is not configured')."""
    errors: dict[str, str] = {}
    for payload in payloads:
        for result in payload.get("results", []):
            report = result.get("report")
            if isinstance(report, dict) and "error" in report:
                errors.setdefault(result.get("name"), result.get("result", report["error"]))
    return [{"ne_name": name, "error": error} for name, error in errors.items()]


def _common_cell_name_pattern(cell_names: list[str]) -> str:
    """Longest common leading '_'-separated token run across all Cell name values."""
    token_lists = [name.split("_") for name in cell_names if name]
    if not token_lists:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No hay valores de 'Cell name' para derivar el patrón",
        )
    distinct_names = {name for name in cell_names if name}
    if len(distinct_names) == 1:
        return token_lists[0][0]

    common_tokens: list[str] = []
    for tokens in zip(*token_lists):
        if len(set(tokens)) == 1:
            common_tokens.append(tokens[0])
        else:
            break
    if not common_tokens:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se encontró un patrón común entre los 'Cell name' devueltos",
        )
    return "_".join(common_tokens)


@router.post(
    "/mml/cell-summary-lte",
    summary="Consultar resumen de celdas LTE",
    description=(
        "Ejecuta `DSP CELL:;` y `LST CELL:;` para el lote de nodos indicado. "
        "Combina los datos por nombre de nodo e identificador de celda. "
        "Los datos válidos aparecen en `records` y los nodos con errores en `errors`."
    ),
    response_description="Resumen de celdas LTE y errores por nodo.",
    responses=_MML_RESPONSES,
)
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


@router.post(
    "/mml/cell-summary-nr",
    summary="Consultar resumen de celdas NR",
    description=(
        "Ejecuta `DSP NRCELL:;`, `LST NRDUCELL:;` y `LST NRDUCELLTRP:;` "
        "para el lote de nodos indicado. Combina los datos por nombre de nodo "
        "e identificador de celda. Los datos válidos aparecen en `records` y "
        "los nodos con errores en `errors`."
    ),
    response_description="Resumen de celdas NR y errores por nodo.",
    responses=_MML_RESPONSES,
)
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


@router.post(
    "/mml/cell-summary-umts",
    summary="Consultar resumen de celdas UMTS de un NodeB",
    description=(
        "Ejecuta `DSP UCELL:DSPT=BYNODEB` contra la lista fija de RNC para "
        "ubicar el NodeB, deriva el patrón común de sus `Cell name` y ejecuta "
        "`LST UCELL:LSTTYPE=ByCellName` en la(s) RNC donde fue encontrado. "
        "Combina ambos resultados por `Cell ID`."
    ),
    response_description="Resumen de celdas UMTS del NodeB y errores por RNC.",
    responses=_MML_RESPONSES,
)
async def create_cell_summary_umts(
    request: UmtsCellSummaryRequest,
    user_id: str = Depends(require_user),
):
    """Ubica un NodeB entre las RNC fijas y extrae el estado/configuración de sus celdas UMTS."""
    dsp_command = f'DSP UCELL:DSPT=BYNODEB,NODEBNAME="{request.nodeb_name}";'
    dsp_payload = await _execute_mml(dsp_command, _umts_rnc_names())

    matched_rnc_names = _successful_ne_names(dsp_payload)
    if not matched_rnc_names:
        return {
            "nodeb_name": request.nodeb_name,
            "rnc_names_matched": [],
            "pattern": None,
            "commands": [dsp_command],
            "records": [],
            "count": 0,
            "errors": _umts_ne_errors(dsp_payload),
        }

    dsp_dataframe = _records_dataframe(dsp_payload, "DSP UCELL", key_column="Cell ID")[[
        "ne_name",
        "Cell ID",
        "Cell name",
        "Operation state",
    ]]

    pattern = _common_cell_name_pattern(dsp_dataframe["Cell name"].tolist())
    lst_command = f'LST UCELL:LSTTYPE=ByCellName,CELLNAME="{pattern}";'
    lst_payload = await _execute_mml(lst_command, matched_rnc_names)
    lst_dataframe = _records_dataframe(lst_payload, "LST UCELL", key_column="Cell ID")[[
        "ne_name",
        "Cell ID",
        "Max Transmit Power of Cell",
        "Band Indicator",
        "Downlink UARFCN",
    ]]

    summary_dataframe = dsp_dataframe.merge(
        lst_dataframe,
        on=["ne_name", "Cell ID"],
        how="left",
        validate="one_to_one",
    )
    summary_dataframe = summary_dataframe.astype(object).where(summary_dataframe.notna(), None)

    return {
        "nodeb_name": request.nodeb_name,
        "rnc_names_matched": matched_rnc_names,
        "pattern": pattern,
        "commands": [dsp_command, lst_command],
        "records": summary_dataframe.to_dict(orient="records"),
        "count": len(summary_dataframe),
        "errors": _umts_ne_errors(dsp_payload, lst_payload),
    }
