
from fastapi import FastAPI
from app.api.v1.router import api_v1

app = FastAPI(title="ML-Portal API")

# health endpoints without /api/v1 for infra health checks
@app.get("/healthz")
async def healthz():
    return {"status": "healthy"}

@app.get("/readyz")
async def readyz():
    return {"status": "ready", "dependencies": {}}

@app.get("/version")
async def version():
    return {"version": "0.0.0", "build_time": "", "git_commit": ""}

# Versioned API
app.include_router(api_v1, prefix="/api/v1")
