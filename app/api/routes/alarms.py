from datetime import datetime
from zoneinfo import ZoneInfo
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
import httpx
import logging

from app.api.routes.auth import require_user
from app.services.huawei_client import get_client, get_huawei_headers, mark_huawei_activity

router = APIRouter(tags=["Alarms"])
logger = logging.getLogger(__name__)

_CHILE_TZ = ZoneInfo("America/Santiago")


# Convención Huawei/ITU X.733 asumida, no confirmada contra el MAE real; fallback al código crudo si no coincide.
_SEVERITY_LABELS = {
    "1": "Crítica",
    "2": "Mayor",
    "3": "Menor",
    "4": "Advertencia",
    "5": "Indeterminada",
}
_ACK_STATE_LABELS = {"0": "No reconocida", "1": "Reconocida"}
_CLEARED_LABELS = {"0": "Activa", "1": "Limpia"}

_ALARM_RESPONSES = {
    400: {"description": "Parámetros inválidos (dataType/baseObjectInstance/marker rechazados por Huawei)."},
    401: {"description": "Falta el token o no es válido."},
    502: {"description": "No fue posible completar la comunicación con Huawei."},
}

# Lista fija de alarmId monitoreadas por el caso de uso "Hermes".
_HERMES_ALARM_IDS = ["13882", "22214", "22224", "301", "40012"]
_HERMES_FILTER = json.dumps([{"field": "alarmId", "operator": "IN", "values": _HERMES_ALARM_IDS}])


def _epoch_ms_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return value
    # 0 means "not cleared" for active alarms, not an actual 1970 timestamp.
    if millis == 0:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=_CHILE_TZ).isoformat()


def _simplify_alarm(raw: dict) -> dict:
    return {
        "alarmId": raw.get("alarmId"),
        "alarmName": raw.get("alarmName"),
        "meName": raw.get("meName"),
        "objectInstance": raw.get("objectInstance"),
        "perceivedSeverity": _SEVERITY_LABELS.get(raw.get("perceivedSeverity"), raw.get("perceivedSeverity")),
        "alarmRaisedTime": _epoch_ms_to_iso(raw.get("alarmRaisedTime")),
        "alarmClearedTime": _epoch_ms_to_iso(raw.get("alarmClearedTime")),
        "cleared": _CLEARED_LABELS.get(raw.get("cleared"), raw.get("cleared")),
        "ackState": _ACK_STATE_LABELS.get(raw.get("ackState"), raw.get("ackState")),
        "comments": raw.get("comments"),
        "additionalInformation": raw.get("additionalInformation"),
    }


def _simplify_hermes_alarm(raw: dict) -> dict:
    return {
        "Alarm ID": raw.get("alarmId"),
        "Alarm name": raw.get("alarmName"),
        "Comment": raw.get("comments"),
        "MO Name": raw.get("nativeMoName"),
        "Occurred On (NT)": _epoch_ms_to_iso(raw.get("alarmRaisedTime")),
        "Cleared On (NT)": _epoch_ms_to_iso(raw.get("alarmClearedTime")),
        "Log Serial Number": raw.get("csn"),
    }


async def _request_alarms(params: dict) -> dict:
    """Query Huawei's alarms endpoint with the given query params."""
    client = get_client()
    try:
        response = await client.get(
            "/api/rest/faultSupervisonManagement/v1/alarms",
            headers=await get_huawei_headers(),
            params=params,
        )
        response.raise_for_status()
        mark_huawei_activity()
    except httpx.HTTPStatusError as error:
        try:
            error_payload = error.response.json()
        except ValueError:
            error_payload = None
        if isinstance(error_payload, dict) and error_payload.get("retMessage"):
            logger.error(
                "Huawei alarms request rejected: HTTP %s retCode=%s retMessage=%s",
                error.response.status_code,
                error_payload.get("retCode"),
                error_payload.get("retMessage"),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_payload["retMessage"],
            ) from error
        logger.exception("Huawei alarms request returned an HTTP error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei alarms request failed",
        ) from error
    except httpx.ProxyError as error:
        logger.exception("Huawei alarms request blocked by proxy: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei alarms request blocked by proxy (check proxy ACL for the Huawei host)",
        ) from error
    except httpx.HTTPError as error:
        logger.exception("Huawei alarms request could not be completed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Huawei alarms request could not be completed",
        ) from error

    return response.json()


async def _get_current_alarms(site_name: str, limit: int, marker: str | None) -> dict:
    """Query current (active) alarms for a site from Huawei's alarms endpoint."""
    params: dict = {"dataType": "CURRENT", "baseObjectInstance": site_name, "limit": limit}
    if marker:
        params["marker"] = marker
    return await _request_alarms(params)


async def _get_hermes_alarms(limit: int, marker: str | None) -> dict:
    """Query active alarms across the whole network, filtered to the Hermes alarmId list."""
    params: dict = {
        "dataType": "CURRENT",
        "alarmAckState": "ALL_ACTIVE_ALARMS",
        "filter": _HERMES_FILTER,
        "limit": limit,
    }
    if marker:
        params["marker"] = marker
    return await _request_alarms(params)


@router.get(
    "/alarms/hermes",
    summary="Consultar alarmas activas del caso Hermes (lista fija de alarmId)",
    description=(
        "Consulta las alarmas actuales (`dataType=CURRENT`, `alarmAckState=ALL_ACTIVE_ALARMS`) "
        "en toda la red, filtradas por una lista fija de `alarmId` "
        f"({', '.join(_HERMES_ALARM_IDS)}), y devuelve un JSON aplanado listo para "
        "convertir a DataFrame."
    ),
    response_description="Alarmas Hermes activas, con marker para paginar si aplica.",
    responses=_ALARM_RESPONSES,
)
async def get_hermes_alarms(
    limit: int = Query(500, ge=1, le=1000),
    marker: str | None = Query(None),
    user_id: str = Depends(require_user),
):
    """Consulta alarmas CURRENT filtradas por la lista fija de alarmId de Hermes."""
    payload = await _get_hermes_alarms(limit, marker)
    alarms = [_simplify_hermes_alarm(raw) for raw in payload.get("alarmInformationList", [])]

    return {
        "alarms": alarms,
        "count": len(alarms),
        "marker": payload.get("marker"),
    }


@router.get(
    "/alarms/{site_name}",
    summary="Consultar alarmas activas de un sitio",
    description=(
        "Consulta las alarmas actuales (`dataType=CURRENT`) de un sitio Huawei "
        "(`baseObjectInstance`) y devuelve una lista simplificada pensada para "
        "soporte, con severidad/estado traducidos a texto y fechas en hora de "
        "Chile continental (ISO 8601). `alarmClearedTime` es `null` en alarmas "
        "activas (aún no limpiadas)."
    ),
    response_description="Alarmas activas del sitio, con marker para paginar si aplica.",
    responses=_ALARM_RESPONSES,
)
async def get_site_alarms(
    site_name: str,
    limit: int = Query(500, ge=1, le=1000),
    marker: str | None = Query(None),
    user_id: str = Depends(require_user),
):
    """Consulta alarmas CURRENT de un sitio y las devuelve en formato reducido."""
    payload = await _get_current_alarms(site_name, limit, marker)
    alarms = [_simplify_alarm(raw) for raw in payload.get("alarmInformationList", [])]

    return {
        "site_name": site_name,
        "alarms": alarms,
        "count": len(alarms),
        "marker": payload.get("marker"),
    }
