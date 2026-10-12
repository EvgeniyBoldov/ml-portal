"""Production graph worker: models and credentials are owned by the API."""
from contextlib import asynccontextmanager
from fastapi import FastAPI

from common import CLIENT, POOL
from portal import ENGINES, router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    POOL.shutdown(wait=True)
    for engine in ENGINES.values():
        engine.close()
    CLIENT.close()


app = FastAPI(title="LongMemory HippoRAG", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_configuration": "api_registry"}
