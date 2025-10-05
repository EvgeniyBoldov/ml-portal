
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.router import api_v1
# from core.middleware import TenantMiddleware
from core.health import health_checker
# from core.observability import TracingMiddleware
# from core.idempotency import IdempotencyMiddleware

app = FastAPI(title="ML-Portal API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware (order matters: tracing -> idempotency -> tenant)
# app.add_middleware(TracingMiddleware)
# app.add_middleware(IdempotencyMiddleware)
# app.add_middleware(TenantMiddleware)

# health endpoints without /api/v1 for infra health checks
@app.get("/healthz")
async def healthz():
    """Liveness probe - basic health check"""
    return {"status": "healthy"}

@app.get("/readyz")
async def readyz():
    """Readiness probe - check critical dependencies"""
    health_result = await health_checker.check_critical()
    return health_result

@app.get("/health")
async def health():
    """Detailed health check with all services"""
    health_result = await health_checker.check_all()
    return health_result

@app.get("/version")
async def version():
    return {"version": "0.0.0", "build_time": "", "git_commit": ""}

# Versioned API
app.include_router(api_v1, prefix="/api/v1")