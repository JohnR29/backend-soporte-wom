from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.huawei import router as huawei_router
from app.services.huawei_client import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(title="backend-soporte", lifespan=lifespan)
app.include_router(huawei_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
