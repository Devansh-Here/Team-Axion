"""Read-only executor: guard ke baad bhi SQL yahan 4 layers se guzarta hai.
1) mode=ro connection  2) query_only pragma  3) authorizer (default deny)
4) progress handler (timeout) + row/byte cap.
Error messages kabhi raw return nahi karte (schema/column leak na ho).
"""
import sqlite3
import time
from pathlib import Path

from app.contracts import QueryOutcome

_SQLITE_OK = 0
_SQLITE_DENY = 1
_READ = 20
_SELECT = 21
_FUNCTION = 31
_RECURSIVE = 33

_ALLOWED_ACTIONS = {_READ, _SELECT, _FUNCTION, _RECURSIVE}
_DENIED_FUNCTIONS = {
    "load_extension", "readfile", "writefile", "randomblob", "zeroblob",
    "edit", "fts3_tokenizer",
}


def _authorizer(action, arg1, arg2, db_name, source):
    if action not in _ALLOWED_ACTIONS:
        return _SQLITE_DENY  # INSERT/UPDATE/DELETE/CREATE/DROP/ATTACH/PRAGMA sab deny
    if action == _FUNCTION and (arg2 or "").lower() in _DENIED_FUNCTIONS:
        return _SQLITE_DENY
    if action == _READ and (arg1 or "").lower().startswith("sqlite_"):
        return _SQLITE_DENY
    return _SQLITE_OK


def _fail(status, code, started):
    return QueryOutcome(status=status, error_code=code,
                        elapsed_ms=int((time.monotonic() - started) * 1000))


def execute_read_only(db_path: str, sql: str, params: list, *, timeout_s: float,
                      max_rows: int, max_bytes: int) -> QueryOutcome:
    started = time.monotonic()
    conn = None
    try:
        path = Path(db_path).resolve()
        if not path.is_file():
            return _fail("ERROR", "DB_NOT_FOUND", started)

        conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True,
                               timeout=1.0, isolation_level=None)
        conn.execute("PRAGMA query_only = ON")
        conn.set_authorizer(_authorizer)

        deadline = started + timeout_s
        timed_out = {"hit": False}

        def _progress():
            if time.monotonic() > deadline:
                timed_out["hit"] = True
                return 1
            return 0

        conn.set_progress_handler(_progress, 1000)

        try:
            cur = conn.execute(sql, list(params or []))
            columns = [d[0] for d in (cur.description or [])]
            rows, size, truncated = [], 0, False
            while True:
                batch = cur.fetchmany(100)
                if not batch:
                    break
                for row in batch:
                    clean = [("<blob>" if isinstance(v, (bytes, bytearray)) else v)
                             for v in row]
                    size += len(repr(clean))
                    if len(rows) >= max_rows or size > max_bytes:
                        truncated = True
                        break
                    rows.append(clean)
                if truncated:
                    break
        except sqlite3.Error as e:
            if timed_out["hit"]:
                return _fail("TIMEOUT", "QUERY_TIMEOUT", started)
            msg = str(e).lower()
            if "not authorized" in msg or "readonly" in msg or "read-only" in msg:
                return _fail("REJECTED", "NOT_AUTHORIZED", started)
            return _fail("ERROR", "SQL_ERROR", started)

        if timed_out["hit"]:
            return _fail("TIMEOUT", "QUERY_TIMEOUT", started)

        return QueryOutcome(
            status="OK", columns=columns, rows=rows, row_count=len(rows),
            truncated=truncated,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except Exception:
        return _fail("ERROR", "EXECUTOR_ERROR", started)
    finally:
        if conn is not None:
            conn.close()