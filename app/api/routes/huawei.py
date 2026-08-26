from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from pydantic import BaseModel, Field
import logging

from app.api.routes.auth import require_user
from app.services.huawei_client import get_client, get_huawei_headers
from app.services.mml_parser import MMLAutoParser

router = APIRouter(tags=["mml"])
logger = logging.getLogger(__name__)


class MmlCommandRequest(BaseModel):
    command: str = Field(min_length=1)
    ne_names: list[str] = Field(min_length=1, max_length=100)


@router.post("/mml/command")
async def execute_mml_command(
    request: MmlCommandRequest,
    user_id: str = Depends(require_user),
):
    """Execute one synchronous MML command against up to 100 network elements."""
    client = get_client()
    try:
        response = await client.post(
            "/api/rest/mmlManagement/v1/command",
            headers=await get_huawei_headers(),
            json={"command": request.command, "neNames": request.ne_names},
        )
        response.raise_for_status()
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
