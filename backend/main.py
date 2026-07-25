"""
main.py
FastAPI app entrypoint. Mounts routes, sets up CORS for the Streamlit/React
frontend, exposes a root health-check, and installs a global exception handler
so that any unhandled exception is logged and returned as a clean JSON 500
instead of a raw FastAPI traceback.

Run with:
    uvicorn main:app --reload --port 8000
"""
import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.routes import router as api_router

# ---------------------------------------------------------------------------
# Logging — structured, visible in uvicorn's output
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Debt Radar API",
    description=(
        "Scans a repo's static code smells + git churn history to rank "
        "technical-debt hotspots."
    ),
    version="0.1.0",
)

# Wide-open CORS for the hackathon demo (Streamlit frontend runs on a different port).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


# ---------------------------------------------------------------------------
# Global exception handler — last-resort safety net
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch any exception that slipped past all route-level handlers.
    Log the full traceback server-side and return a clean JSON 500
    (never expose raw Python tracebacks to the client).
    """
    tb = traceback.format_exc()
    logger.error(
        "Unhandled exception on %s %s\n%s",
        request.method,
        request.url.path,
        tb,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                f"An unexpected server error occurred: {type(exc).__name__}: {exc}. "
                "Please check the server logs for details."
            )
        },
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/")
def root() -> dict:
    return {"name": "Debt Radar API", "status": "running", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
