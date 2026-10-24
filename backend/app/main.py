"""FastAPI /api/v1. Safe errors only, role server-side, loopback only.
Run: uvicorn app.main:app --host 127.0.0.1 --port 8000
"""
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config, metadata_db
from app.agent import analyze
from app.contracts import AnalysisRequest
from app.policy import permitted_schema, resolve_role

MAX_QUESTION_CHARS = 2000
_PROTECTED_KEYS = {"salary"}  # protected column naam (kisi bhi level pe drop)


class ApiError(Exception):
    def __init__(self, status, code, message, run_id=None, retryable=False):
        self.status, self.code, self.message = status, code, message
        self.run_id, self.retryable = run_id, retryable


def _err_response(status, code, message, run_id=None, retryable=False):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message,
                           "run_id": run_id, "retryable": retryable}},
    )


def _strip(obj):
    """Protected keys ko response se hata do (profile/evidence dono ke liye)."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items()
                if str(k).lower().split(".")[-1] not in _PROTECTED_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


@asynccontextmanager
async def lifespan(app):
    metadata_db.init_db()
    demo = Path(config.DATA_DIR) / "demo" / "demo.sqlite"
    if demo.is_file():
        metadata_db.upsert_dataset("demo", str(demo))
    yield


app = FastAPI(title="Hypnexis AI-02", lifespan=lifespan)
router = APIRouter(prefix="/api/v1")


@app.exception_handler(ApiError)
async def _api_error(request: Request, exc: ApiError):
    return _err_response(exc.status, exc.code, exc.message, exc.run_id, exc.retryable)


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    return _err_response(422, "INVALID_REQUEST", "Request is not valid.")


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return _err_response(exc.status_code, code, "Request could not be completed.")


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    # details kabhi nahi: na trace, na path, na message
    return _err_response(500, "INTERNAL_ERROR", "Something went wrong.",
                         run_id=str(uuid.uuid4()), retryable=True)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/datasets")
def datasets():
    return {"datasets": metadata_db.list_datasets()}


@router.get("/datasets/{dataset_id}/schema")
def dataset_schema(dataset_id: str):
    schema = permitted_schema(resolve_role(), dataset_id)
    if not schema:
        raise ApiError(404, "DATASET_NOT_FOUND", "Dataset not found.")
    return {"dataset_id": dataset_id, "tables": schema}


@router.get("/datasets/{dataset_id}/profile")
def dataset_profile(dataset_id: str):
    schema = permitted_schema(resolve_role(), dataset_id)
    ds = metadata_db.get_dataset(dataset_id)
    if not schema or ds is None:
        raise ApiError(404, "DATASET_NOT_FOUND", "Dataset not found.")
    conn = None
    try:
        from app.profiler import profile_columns
        uri = f"{Path(ds['db_path']).resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        profile = profile_columns(conn, list(schema))
    except Exception:
        raise ApiError(503, "PROFILE_UNAVAILABLE", "Profile is not available.",
                       retryable=True)
    finally:
        if conn is not None:
            conn.close()
    return {"dataset_id": dataset_id, "profile": _strip(profile)}


@router.post("/analyze")
def analyze_route(req: AnalysisRequest):
    if not req.question.strip() or len(req.question) > MAX_QUESTION_CHARS:
        raise ApiError(422, "INVALID_QUESTION", "Question is empty or too long.")
    role = resolve_role()  # client se role kabhi nahi
    try:
        outcome = analyze(req, role)
    except Exception:
        raise ApiError(500, "ANALYSIS_FAILED", "Analysis failed.",
                       run_id=str(uuid.uuid4()), retryable=True)
    try:
        metadata_db.save_run(outcome.run_id, req.dataset_id, outcome.status, req.question)
        metadata_db.add_audit_event(outcome.run_id, "analyze",
                                    {"dataset_id": req.dataset_id, "status": outcome.status})
    except Exception:
        pass  # logging fail hone se user ka answer nahi rukna chahiye
    return outcome


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    run = metadata_db.get_run(run_id)
    if run is None:
        raise ApiError(404, "RUN_NOT_FOUND", "Run not found.", run_id=run_id)
    return run


@router.get("/runs/{run_id}/evidence")
def get_run_evidence(run_id: str):
    ev = metadata_db.get_evidence_by_run(run_id)
    if ev is None:
        raise ApiError(404, "EVIDENCE_NOT_FOUND", "Evidence not found.", run_id=run_id)
    return _strip(ev)


@router.get("/audit")
def audit(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return {"events": metadata_db.list_audit_events(limit=limit, offset=offset),
            "limit": limit, "offset": offset}


app.include_router(router)