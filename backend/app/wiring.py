"""Wires Lane A to the real Lane B/C functions. Nothing here is built until default_deps() is called."""
import hashlib
import sqlite3

from app import config, metadata_db
from app.agent import Deps
from app.audit import write_audit_event
from app.evidence import make_evidence_saver
from app.executor import execute_read_only
from app.model_client import ModelClient
from app.policy import authorize
from app.profiler import profile_columns
from app.result_checks import validate_result
from app.schema_recovery import recover_permitted_schema
from app.sql_guard import validate_candidate


def _db_path(dataset_id: str) -> str:
    row = metadata_db.get_dataset(dataset_id)
    if not row:
        raise ValueError("unknown dataset")
    return row["db_path"]          # CONFIRM this key name (see Step 3)


def _dataset_sha256(dataset_id: str):
    """SHA-256 of the registered DB file at run time (measured, not assumed)."""
    h = hashlib.sha256()
    with open(_db_path(dataset_id), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def default_deps(role: str) -> Deps:
    metadata_db.init_db()           # makes sure metadata tables exist (evidence/audit)
    client = ModelClient()          # reads MODEL_BASE_URL / MODEL_NAME, loopback only

    def get_profile(dataset_id: str, tables: list) -> dict:
        conn = sqlite3.connect(f"file:{_db_path(dataset_id)}?mode=ro", uri=True)   # read-only
        try:
            return profile_columns(conn, tables)
        finally:
            conn.close()

    def get_schema(dataset_id: str) -> dict[str, list[str]]:
        return recover_permitted_schema(_db_path(dataset_id), role, dataset_id)

    def authorize_dynamic(current_role: str, dataset_id: str, question: str):
        return authorize(current_role, dataset_id, question,
                         schema_override=get_schema(dataset_id))

    def execute(dataset_id: str):
        def run(sql: str, params: list):
            return execute_read_only(
                _db_path(dataset_id), sql, params,
                timeout_s=config.MAX_QUERY_SECONDS,
                max_rows=min(config.MAX_RESULT_ROWS, 5000 if role == "owner" else 500 if role == "analyst" else 100),
                max_bytes=config.MAX_RESULT_BYTES,
            )
        return run

    deps = Deps(
        authorize=authorize_dynamic,
        get_schema=get_schema,
        get_profile=get_profile,
        guard=validate_candidate,
        execute=lambda ds, sql, params: execute(ds)(sql, params),
        validate_result=validate_result,
        generate=client.generate,
        audit=write_audit_event,
        save_evidence=make_evidence_saver(metadata_db.save_evidence, config.MODEL_NAME, _dataset_sha256),
    )
    return deps
