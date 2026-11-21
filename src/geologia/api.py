# GEOLOGIA foundation API.
# Honest nucleus: health + read-only engine registry + deterministic planner
# + retrieval-only knowledge base + dataset verification + gated task ledger.
# No scientific engine is installed or executed in this phase.
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from geologia import __version__
from geologia.data_layer import records as ds
from geologia.data_layer import tasks as tl
from geologia.knowledge.retrieval import get_kb
from geologia.planner import UnknownDomainError, build_plan, list_planner_domains
from geologia.registry import get_engine, list_engines

app = FastAPI(
    title="GEOLOGIA API",
    version=__version__,
    description=(
        "Foundation nucleus: engine registry + planner (plans only) + "
        "retrieval-only knowledge (zero hallucination) + dataset verification "
        "+ task ledger with mandatory gates."
    ),
)


class PlanRequest(BaseModel):
    request: str = Field(..., min_length=3, max_length=2000)
    language: str = Field("ar")
    bbox: Optional[List[float]] = None


class KnowledgeQuery(BaseModel):
    query: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(5, ge=1, le=20)
    scope: str = Field("all")


class DatasetIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    path: str = Field(..., min_length=1, max_length=1024)
    dtype: str = Field("auto")
    declared_crs: Optional[str] = None
    declared_units: Optional[str] = None
    license_status: str = "unknown"
    source_url: Optional[str] = None
    derived_from: Optional[str] = None
    notes: str = ""


class TransitionIn(BaseModel):
    to_state: str
    reason: str = ""
    language: str = "ar"


class TaskIn(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    engine_id: str
    dataset_ids: List[str]
    params: Optional[dict] = None
    isolation: Optional[dict] = None
    notes: str = ""


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "geologia",
        "version": __version__,
        "engines_integrated": 0,
        "acceptance_standard": "digest_10_acceptance_standard.md",
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


@app.get("/api/v1/domains")
def domains() -> dict:
    items = list_planner_domains()
    return {"count": len(items), "domains": items}


@app.post("/api/v1/plans")
def create_plan(body: PlanRequest) -> dict:
    if body.language not in ("ar", "en"):
        raise HTTPException(status_code=422, detail="language must be 'ar' or 'en'")
    if body.bbox is not None and len(body.bbox) != 4:
        raise HTTPException(status_code=422, detail="bbox must have 4 numbers")
    try:
        return build_plan(body.request, body.language, body.bbox)
    except UnknownDomainError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "unknown_domain",
                "message": exc.message,
                "supported_domains": exc.supported_domains,
            },
        )


# ---------------------------------------------------------------------------
# Knowledge layer: retrieval-only, citations mandatory, honest misses.
# ---------------------------------------------------------------------------
@app.get("/api/v1/knowledge/stats")
def knowledge_stats() -> dict:
    return get_kb().stats()


@app.get("/api/v1/knowledge/catalog")
def knowledge_catalog() -> dict:
    from geologia.knowledge.catalog import catalog_to_dicts
    entries = catalog_to_dicts()
    return {
        "count": len(entries),
        "entries": [
            {
                "entry_id": e["entry_id"],
                "title_ar": e["title_ar"],
                "author": e["author"],
                "year": e.get("year"),
                "origin_type": e["origin_type"],
                "region_scope": e["region_scope"],
                "confidence": e["confidence"],
                "source_url": e.get("source_url"),
            }
            for e in entries
        ],
    }


@app.post("/api/v1/knowledge/query")
def knowledge_query(body: KnowledgeQuery) -> dict:
    if body.scope not in ("all", "catalog", "digest", "engine_kb", "user_corpus"):
        raise HTTPException(status_code=422,
                            detail="scope must be all|catalog|digest|engine_kb|user_corpus")
    return get_kb().search(body.query, top_k=body.top_k, scope=body.scope)


# ---------------------------------------------------------------------------
# Dataset verification layer: register -> checksum -> validate -> usable.
# ---------------------------------------------------------------------------
@app.get("/api/v1/datasets")
def datasets() -> dict:
    items = ds.list_datasets()
    return {"count": len(items), "datasets": items}


@app.get("/api/v1/datasets/{dataset_id}")
def dataset_detail(dataset_id: str) -> dict:
    record = ds.get_dataset(dataset_id)
    if record is None:
        raise HTTPException(status_code=404, detail="dataset_id not found")
    return record


@app.post("/api/v1/datasets")
def register_dataset(body: DatasetIn) -> dict:
    try:
        record = ds.register_dataset(
            name=body.name, path=body.path, dtype=body.dtype,
            declared_crs=body.declared_crs, declared_units=body.declared_units,
            license_status=body.license_status, source_url=body.source_url,
            derived_from=body.derived_from, notes=body.notes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return record


@app.post("/api/v1/datasets/{dataset_id}/validate")
def validate_dataset(dataset_id: str) -> dict:
    try:
        return ds.validate_dataset(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset_id not found")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/v1/datasets/{dataset_id}/verify-checksum")
def verify_checksum(dataset_id: str) -> dict:
    try:
        return ds.verify_checksum(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="dataset_id not found")


# ---------------------------------------------------------------------------
# Task ledger: create planned tasks; execution is gated on certification.
# ---------------------------------------------------------------------------
@app.get("/api/v1/tasks")
def tasks() -> dict:
    items = tl.list_tasks()
    return {"count": len(items), "tasks": items}


@app.get("/api/v1/tasks/{task_id}")
def task_detail(task_id: str) -> dict:
    task = tl.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_id not found")
    return task


@app.post("/api/v1/tasks")
def create_task(body: TaskIn) -> dict:
    try:
        return tl.create_task(
            title=body.title, engine_id=body.engine_id,
            dataset_ids=body.dataset_ids, params=body.params,
            isolation=body.isolation, notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/v1/tasks/{task_id}/transition")
def task_transition(task_id: str, body: TransitionIn) -> dict:
    try:
        return tl.transition(task_id, body.to_state, body.reason, body.language)
    except KeyError:
        raise HTTPException(status_code=404, detail="task_id not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except tl.TaskGateError as exc:
        raise HTTPException(status_code=409, detail={
            "error": "gate_refused",
            "gate": exc.gate,
            "message": exc.message,
        })
