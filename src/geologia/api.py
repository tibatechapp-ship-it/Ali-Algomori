# GEOLOGIA foundation API.
# Honest nucleus: health + read-only engine registry + deterministic planner.
# No scientific engine is installed or executed in this phase.
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from geologia import __version__
from geologia.planner import build_plan
from geologia.registry import get_engine, list_engines

app = FastAPI(
    title="GEOLOGIA API",
    version=__version__,
    description="Foundation nucleus: engine registry + analysis planner (plans only).",
)


class PlanRequest(BaseModel):
    request: str = Field(..., min_length=3, max_length=2000)
    language: str = Field("ar")
    bbox: Optional[List[float]] = None


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "geologia",
        "version": __version__,
        "engines_integrated": 0,
    }


@app.get("/api/v1/engines")
def engines(domain: Optional[str] = None) -> dict:
    items = list_engines(domain)
    return {"count": len(items), "engines": items}


@app.get("/api/v1/engines/{engine_id}")
def engine_detail(engine_id: str) -> dict:
    card = get_engine(engine_id)
    if card is None:
        raise HTTPException(status_code=404, detail="engine_id not found in registry")
    return card


@app.post("/api/v1/plans")
def create_plan(body: PlanRequest) -> dict:
    if body.language not in ("ar", "en"):
        raise HTTPException(status_code=422, detail="language must be 'ar' or 'en'")
    if body.bbox is not None and len(body.bbox) != 4:
        raise HTTPException(status_code=422, detail="bbox must have 4 numbers")
    return build_plan(body.request, body.language, body.bbox)
