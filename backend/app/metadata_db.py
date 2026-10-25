"""Metadata DB: datasets, runs, evidence, audit_events.
Analytical DB se alag file. Sirf parameterised SQL (?), kabhi string concat nahi.
"""
import json
import sqlite3
import time
from contextlib import contextmanager

from app import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    db_path    TEXT NOT NULL,
    sha256     TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    dataset_id  TEXT,
    status      TEXT,
    question    TEXT,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    run_id      TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     TEXT,
    event_type TEXT,
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id);
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    question TEXT NOT NULL,
    effective_question TEXT NOT NULL,
    status TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_turns ON conversation_turns(conversation_id, turn_index);
"""


@contextmanager
def _conn(path: str | None = None):
    c = sqlite3.connect(path or config.METADATA_DB, timeout=5.0)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db(path: str | None = None) -> None:
    import os
    p = path or config.METADATA_DB
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with _conn(p) as c:
        c.executescript(_SCHEMA)


# ---------- datasets ----------
def upsert_dataset(dataset_id, db_path, sha256=None, path=None):
    with _conn(path) as c:
        c.execute(
            "INSERT OR REPLACE INTO datasets (dataset_id, db_path, sha256, created_at) "
            "VALUES (?,?,?,?)", (dataset_id, db_path, sha256, time.time()))


def get_dataset(dataset_id, path=None):
    with _conn(path) as c:
        r = c.execute("SELECT dataset_id, db_path, sha256 FROM datasets WHERE dataset_id=?",
                      (dataset_id,)).fetchone()
    return None if r is None else {"dataset_id": r[0], "db_path": r[1], "sha256": r[2]}


def list_datasets(path=None):
    with _conn(path) as c:
        rows = c.execute("SELECT dataset_id FROM datasets ORDER BY dataset_id").fetchall()
    return [r[0] for r in rows]


# ---------- runs ----------
def save_run(run_id, dataset_id, status, question, path=None):
    with _conn(path) as c:
        c.execute(
            "INSERT OR REPLACE INTO runs (run_id, dataset_id, status, question, created_at) "
            "VALUES (?,?,?,?,?)", (run_id, dataset_id, status, question, time.time()))


def get_run(run_id, path=None):
    with _conn(path) as c:
        r = c.execute("SELECT run_id, dataset_id, status, question, created_at "
                      "FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if r is None:
        return None
    return {"run_id": r[0], "dataset_id": r[1], "status": r[2],
            "question": r[3], "created_at": r[4]}


# ---------- evidence ----------
def save_evidence(evidence_id, run_id, payload: dict, path=None):
    with _conn(path) as c:
        c.execute(
            "INSERT OR REPLACE INTO evidence (evidence_id, run_id, payload, created_at) "
            "VALUES (?,?,?,?)",
            (evidence_id, run_id, json.dumps(payload, default=str), time.time()))


def get_evidence(evidence_id, path=None):
    with _conn(path) as c:
        r = c.execute("SELECT payload FROM evidence WHERE evidence_id=?",
                      (evidence_id,)).fetchone()
    return None if r is None else json.loads(r[0])


def get_evidence_by_run(run_id, path=None):
    with _conn(path) as c:
        r = c.execute("SELECT payload FROM evidence WHERE run_id=? "
                      "ORDER BY created_at DESC LIMIT 1", (run_id,)).fetchone()
    return None if r is None else json.loads(r[0])


# ---------- audit ----------
def add_audit_event(run_id, event_type, payload: dict, path=None):
    with _conn(path) as c:
        c.execute(
            "INSERT INTO audit_events (run_id, event_type, payload, created_at) "
            "VALUES (?,?,?,?)",
            (run_id, event_type, json.dumps(payload, default=str), time.time()))


def list_audit_events(limit=50, offset=0, path=None):
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with _conn(path) as c:
        rows = c.execute(
            "SELECT id, run_id, event_type, payload, created_at FROM audit_events "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return [{"id": r[0], "run_id": r[1], "event_type": r[2],
             "payload": json.loads(r[3]), "created_at": r[4]} for r in rows]


def list_conversation_questions(conversation_id, path=None):
    with _conn(path) as c:
        rows = c.execute(
            "SELECT question FROM conversation_turns WHERE conversation_id=? ORDER BY turn_index",
            (conversation_id,),
        ).fetchall()
    return [row[0] for row in rows]


def save_conversation_turn(conversation_id, dataset_id, question, effective_question, status, path=None):
    now = time.time()
    with _conn(path) as c:
        existing = c.execute(
            "SELECT COALESCE(MAX(turn_index), 0) FROM conversation_turns WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()[0]
        c.execute(
            "INSERT OR IGNORE INTO conversations(conversation_id,dataset_id,created_at,updated_at) VALUES(?,?,?,?)",
            (conversation_id, dataset_id, now, now),
        )
        c.execute(
            "INSERT INTO conversation_turns(conversation_id,turn_index,question,effective_question,status,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (conversation_id, existing + 1, question, effective_question, status, now),
        )
        c.execute("UPDATE conversations SET updated_at=? WHERE conversation_id=?", (now, conversation_id))
