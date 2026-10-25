"""Wires Lane A to the real Lane B/C functions. Nothing here is built until default_deps() is called."""
import sqlite3
from pathlib import Path

from app import config, metadata_db
from app.agent import Deps
from app.audit import write_audit_event
from app.contracts import QueryOutcome
from app.evidence import make_evidence_saver
from app.executor import execute_read_only
from app.model_client import ModelClient
from app.policy import authorize, permitted_schema, protected_column_names, strip_protected, row_filters
from app.profiler import profile_columns
from app.result_checks import validate_result
from app.row_limits import apply_row_filters
from app.sql_guard import validate_candidate
def _live_tables(db_path: str) -> set[str]:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
    finally:
        conn.close()
    return {r[0].lower() for r in rows}


def _db_path(dataset_id: str) -> str:
    row = metadata_db.get_dataset(dataset_id)
    if not row:
        raise ValueError("unknown dataset")
    return row["db_path"]


def default_deps(role: str) -> Deps:
    metadata_db.init_db()           # makes sure metadata tables exist (evidence/audit)
    client = ModelClient()          # reads MODEL_BASE_URL / MODEL_NAME, loopback only

    def get_profile(dataset_id: str, tables: list) -> dict:
        uri = f"{Path(_db_path(dataset_id)).resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)                                  # read-only
        try:
            profile = profile_columns(conn, tables)
            # protected columns ka profile agent/model tak kabhi nahi jaata
            return strip_protected(profile, protected_column_names(dataset_id))
        finally:
            conn.close()

    def execute(dataset_id: str):
        def run(sql: str, params: list):
            try:
                filters = row_filters(role, dataset_id)
                if filters:
                    live = _live_tables(_db_path(dataset_id))
                    if any(t.lower() not in live for t in filters):
                      return QueryOutcome(status="ERROR", error_code="ROW_FILTER_FAILED")
                sql = apply_row_filters(sql, filters)
            except Exception:
                # fail closed: filter na lag paye to unfiltered kabhi nahi chalega
                return QueryOutcome(status="REJECTED", error_code="ROW_FILTER_FAILED")
            return execute_read_only(
                _db_path(dataset_id), sql, params,
                timeout_s=config.MAX_QUERY_SECONDS,
                max_rows=config.MAX_RESULT_ROWS,
                max_bytes=config.MAX_RESULT_BYTES,
            )
        return run

    deps = Deps(
        authorize=authorize,
        get_schema=lambda ds: permitted_schema(role, ds),
        get_profile=get_profile,
        guard=validate_candidate,
        execute=lambda ds, sql, params: execute(ds)(sql, params),
        validate_result=validate_result,
        generate=client.generate,
        audit=write_audit_event,
        save_evidence=make_evidence_saver(metadata_db.save_evidence, config.MODEL_NAME),
    )
    return deps

def test_viewer_blocked_when_filtered_table_renamed(tmp_path, monkeypatch):
    import sqlite3
    from app import wiring

    db = tmp_path / "renamed.sqlite"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE sales_v2(order_id TEXT, region TEXT, net_amt TEXT);
        INSERT INTO sales_v2 VALUES ('O-1','Delhi','100'), ('O-2','Mumbai','900');
    """)
    c.commit()
    c.close()

    monkeypatch.setattr(wiring, "_db_path", lambda ds: str(db))
    monkeypatch.setattr(wiring.metadata_db, "init_db", lambda: None)

    deps = wiring.default_deps("viewer")
    out = deps.execute("demo", "SELECT region, SUM(net_amt) FROM sales_v2 GROUP BY region", [])
    assert out.status != "OK"
    assert out.error_code == "ROW_FILTER_FAILED"