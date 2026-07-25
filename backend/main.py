"""
main.py
FastAPI app entrypoint. Mounts routes, sets up CORS for the Streamlit/React
frontend, and exposes a root health-check.

Run with:
    uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router

app = FastAPI(
    title="Debt Radar API",
    description="Scans a repo's static code smells + git churn history to rank technical-debt hotspots.",
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


@app.get("/")
def root() -> dict:
    return {"name": "Debt Radar API", "status": "running", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
