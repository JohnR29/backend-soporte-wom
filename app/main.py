import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.alarms import router as alarms_router
from app.api.routes.huawei import router as huawei_router
from app.services.huawei_client import close_client, huawei_keepalive_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    keepalive_task = asyncio.create_task(huawei_keepalive_loop())
    yield
    keepalive_task.cancel()
    try:
        await keepalive_task
    except asyncio.CancelledError:
        pass
    await close_client()


app = FastAPI(
    title="Backend de soporte Huawei",
    description=(
        "API intermediaria para ejecutar comandos MML y consultar el estado "
        "de celdas LTE y NR en nodos de la red Huawei. Todas las operaciones "
        "de negocio requieren autenticación mediante token Bearer."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "MML",
            "description": "Ejecución de comandos MML y consultas de celdas por lote de nodos.",
        },
        {
            "name": "Alarms",
            "description": "Consulta de alarmas activas por sitio.",
        },
    ],
    lifespan=lifespan,
)
app.include_router(huawei_router)
app.include_router(alarms_router)


@app.get(
    "/health",
    summary="Comprobar estado del servicio",
    description="Indica si el backend está disponible para recibir solicitudes.",
    response_description="Estado actual del servicio.",
)
async def health():
    return {"status": "ok"}
