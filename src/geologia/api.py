# Honest nucleus: health + read-only engine registry + deterministic planner
# + retrieval-only knowledge base + dataset verification + gated task ledger
# + first-party certified engine execution with evidence reports
# + HTTP upload boundary routing every byte through the reception gate.
import json
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from geologia import __version__
from geologia.data_layer import records as ds
from geologia.data_layer import tasks as tl
from geologia.data_layer import uploads as up
from geologia.data_layer.certification import (
    CertificationRefused,
    certify_engine,
)
from geologia.data_layer.evidence import prove_file
from geologia.data_layer.provenance import ProvenanceLog
from geologia.data_layer.reception import max_upload_bytes
from geologia.knowledge.retrieval import get_kb
from geologia.planner import UnknownDomainError, build_plan, list_planner_domains
from geologia.registry import certified_engines, get_engine, list_engines

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
        "engines_integrated": len(certified_engines()),
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


@app.post("/api/v1/engines/{engine_id}/certify")
def certify(engine_id: str) -> dict:
    """Gate 3: re-run the pinned reference test, record the verdict.
    Third-party engines are refused (integration policy)."""
    try:
        return certify_engine(engine_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except CertificationRefused as exc:
        raise HTTPException(status_code=409, detail={
            "error": "certification_refused",
            "reasons": exc.reasons,
            "message": str(exc),
        })


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
# Upload boundary (ADR-0007): raw octet-stream POST routed through the
# reception gate. The endpoint is deliberately THIN — it enforces the
# transport-side size cap and streams; every other decision belongs to
# data_layer (reception security -> registration -> proof -> provenance).
# ---------------------------------------------------------------------------
@app.get("/api/v1/uploads/policy")
def upload_policy() -> dict:
    """Reception policy a client must respect BEFORE sending bytes."""
    return {
        "method": "POST /api/v1/uploads",
        "body": "application/octet-stream (raw file bytes; no multipart)",
        "max_upload_bytes": max_upload_bytes(),
        "cap_env": "GEOLOGIA_MAX_UPLOAD_BYTES",
        "query_params": {
            "filename": "required — client name; sanitized, never trusted",
            "dtype": "auto|las|csv|geojson|tiff|gpkg (default auto)",
            "declared_crs": "optional declaration, recorded as declared",
            "declared_units": "optional declaration, recorded as declared",
        },
        "verdicts": {
            "200": ["proven", "proven_with_unverified_claims",
                    "needs_review (archive: members must be inspected "
                    "individually)"],
            "413": ["SEC_TOO_LARGE — refused before reading the body"],
            "422": ["rejected (security gate) / refused (content proof)",
                    "rejection codes are evidence, not secrets"],
        },
        "provenance": "every verdict — including refusals — is appended "
                      "to the tamper-evident chain",
        "raw_storage": "immutable content-addressed quarantine; the raw "
                       "upload is never modified",
    }


@app.post("/api/v1/uploads")
async def upload_file(
    request: Request,
    filename: str = Query(..., min_length=1, max_length=255),
    dtype: str = Query("auto"),
    declared_crs: Optional[str] = Query(None, max_length=100),
    declared_units: Optional[str] = Query(None, max_length=100),
) -> dict:
    cap = max_upload_bytes()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > cap:
                raise HTTPException(status_code=413, detail={
                    "error": "upload_too_large",
                    "status": "rejected",
                    "codes": ["SEC_TOO_LARGE"],
                    "message": f"content-length {content_length} exceeds the "
                               f"{cap}-byte reception cap "
                               f"(GEOLOGIA_MAX_UPLOAD_BYTES) — body not read",
                })
        except ValueError:
            raise HTTPException(status_code=400,
                                detail="content-length is not an integer")
    buf = bytearray()
    async for chunk in request.stream():
        if chunk:
            buf.extend(chunk)
            if len(buf) > cap:
                raise HTTPException(status_code=413, detail={
                    "error": "upload_too_large",
                    "status": "rejected",
                    "codes": ["SEC_TOO_LARGE"],
                    "message": f"body exceeded the {cap}-byte reception cap "
                               f"mid-stream — upload aborted",
                })
    result = await run_in_threadpool(
        up.ingest_bytes, bytes(buf), filename, dtype,
        declared_crs, declared_units, ProvenanceLog())
    if result["status"] in ("rejected", "refused"):
        raise HTTPException(status_code=422, detail={
            "error": "upload_refused",
            "status": result["status"],
            "declared_name": result["declared_name"],
            "dataset_id": result["dataset_id"],
            "codes": [f["code"] for f in
                      (result["reception"]["findings"]
                       + (result["proof"] or {}).get("findings", []))
                      if f["severity"] == "error"],
            "reception": result["reception"],
            "proof": result["proof"],
        })
    return result


@app.get("/api/v1/datasets/{dataset_id}/proof")
def dataset_proof(dataset_id: str) -> dict:
    """Re-prove a dataset on demand: one fresh parse, a fresh evidence
    triple, and a new provenance record — proof is an activity, not a
    stored opinion."""
    rec = ds.get_dataset(dataset_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="dataset_id not found")
    if not Path(rec["path"]).exists():
        raise HTTPException(status_code=404, detail={
            "error": "file_missing",
            "message": f"dataset file no longer exists: {rec['path']}",
        })
    report = prove_file(rec["path"], dtype=rec.get("dtype") or "auto",
                        declared_crs=rec.get("declared_crs"),
                        declared_units=rec.get("declared_units"),
                        provenance=ProvenanceLog())
    ds.attach_upload_proof(dataset_id, report)
    return report


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


@app.post("/api/v1/tasks/{task_id}/execute")
def execute_task(task_id: str) -> dict:
    """Run the task's certified engine (gates enforced; 409 if refused)."""
    try:
        return tl.transition(task_id, "executed", reason="api execute")
    except KeyError:
        raise HTTPException(status_code=404, detail="task_id not found")
    except tl.TaskGateError as exc:
        raise HTTPException(status_code=409, detail={
            "error": "gate_refused",
            "gate": exc.gate,
            "message": exc.message,
        })


@app.get("/api/v1/tasks/{task_id}/report")
def task_report(task_id: str) -> dict:
    """Gate 4: the evidence report of an executed task."""
    task = tl.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task_id not found")
    path = task.get("execution_report_path")
    if not path or not Path(path).exists():
        raise HTTPException(status_code=404, detail={
            "error": "no_execution_report",
            "message": "هذه المهمة لم تُنفذ بعد — لا تقرير أدلة",
        })
    return json.loads(Path(path).read_text(encoding="utf-8"))


@app.get("/api/v1/vertical/answer")
def vertical_answer(lat: float, lon: float, model: str = "EGM96") -> dict:
    """T4.2: vertical answer behind the agent-level refusal rule.

    No loaded AND independently verified geoid grid => 409 refusal with the
    coded reason — never an approximate value, never a silent MSL assumption.
    """
    from geologia.data_layer.vertical_rule import answer_vertical
    res = answer_vertical(lat, lon, model)
    if res["status"] != 200:
        raise HTTPException(status_code=res["status"], detail={
            "error": res["error"],
            "missing": res.get("missing", []),
            "message_ar": res["message_ar"],
            "message_en": res["message_en"],
        })
    return res
