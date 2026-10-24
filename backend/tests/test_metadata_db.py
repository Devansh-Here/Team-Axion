import pytest
from app import metadata_db as m


@pytest.fixture
def p(tmp_path):
    path = str(tmp_path / "meta.sqlite")
    m.init_db(path)
    return path


def test_tables_created(p):
    import sqlite3
    c = sqlite3.connect(p)
    names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    c.close()
    assert {"datasets", "runs", "evidence", "audit_events"} <= names


def test_init_is_idempotent(p):
    m.init_db(p)
    m.init_db(p)


def test_dataset_roundtrip(p):
    m.upsert_dataset("demo", "data/demo/demo.sqlite", "abc", path=p)
    assert m.get_dataset("demo", path=p)["db_path"] == "data/demo/demo.sqlite"
    assert m.list_datasets(path=p) == ["demo"]
    assert m.get_dataset("nope", path=p) is None


def test_run_roundtrip(p):
    m.save_run("r1", "demo", "ANSWER", "q", path=p)
    assert m.get_run("r1", path=p)["status"] == "ANSWER"
    assert m.get_run("zzz", path=p) is None


def test_evidence_roundtrip_by_id_and_run(p):
    m.save_evidence("e1", "r1", {"sql": "SELECT 1", "rows": 1}, path=p)
    assert m.get_evidence("e1", path=p)["sql"] == "SELECT 1"
    assert m.get_evidence_by_run("r1", path=p)["rows"] == 1
    assert m.get_evidence("nope", path=p) is None


def test_sql_injection_in_values_is_just_text(p):
    evil = "x'); DROP TABLE runs; --"
    m.save_run("r2", "demo", "ANSWER", evil, path=p)
    assert m.get_run("r2", path=p)["question"] == evil
    assert m.get_run("r2", path=p) is not None


def test_audit_pagination(p):
    for i in range(10):
        m.add_audit_event(f"r{i}", "run", {"n": i}, path=p)
    first = m.list_audit_events(limit=4, offset=0, path=p)
    second = m.list_audit_events(limit=4, offset=4, path=p)
    assert len(first) == 4 and len(second) == 4
    assert first[0]["payload"]["n"] == 9
    assert {e["id"] for e in first}.isdisjoint({e["id"] for e in second})


def test_audit_limit_is_clamped(p):
    assert len(m.list_audit_events(limit=100000, path=p)) <= 200