from fastapi import APIRouter, Depends, HTTPException, status
import httpx
import logging

from app.api.routes.auth import require_user
from app.services.womportal_client import get_tickets_abiertos

router = APIRouter(tags=["Tickets"])
logger = logging.getLogger(__name__)

_TICKET_RESPONSES = {
    401: {"description": "Falta el token o no es válido."},
    502: {"description": "No fue posible completar la comunicación con WOM Portal."},
}


@router.get(
    "/tickets/{sitio}",
    summary="Consultar tickets abiertos de un sitio",
    description="Consulta los tickets de incidencias abiertas de un sitio en WOM Portal.",
    response_description="Respuesta cruda de WOM Portal con los tickets abiertos del sitio.",
    responses=_TICKET_RESPONSES,
)
async def get_tickets(sitio: str, user_id: str = Depends(require_user)):
    try:
        return await get_tickets_abiertos(sitio)
    except httpx.HTTPStatusError as error:
        logger.exception("WOM Portal tickets request returned an HTTP error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="WOM Portal tickets request failed",
        ) from error
    except httpx.HTTPError as error:
        logger.exception("WOM Portal tickets request could not be completed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="WOM Portal tickets request could not be completed",
        ) from error
