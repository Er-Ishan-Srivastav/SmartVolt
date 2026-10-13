"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.routes import router
from app.core import settings

app = FastAPI(
    title=settings.app_name,
    description="Simulation API for prepaid room-level energy meters.",
    version="0.1.0",
)
app.include_router(router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": f"{settings.api_v1_prefix}/health"}
