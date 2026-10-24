import pytest

from app import audit, config, metadata_db


@pytest.fixture
def meta(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "METADATA_DB", str(tmp_path / "a.sqlite"))
    metadata_db.init_db()


def last():
    return metadata_db.list_audit_events(limit=1)[0]


def test_event_is_saved(meta):
    audit.write_audit_event({"run_id": "r1", "event_type": "analyze",
                             "status": "ANSWER", "row_count": 3})
    e = last()
    assert e["run_id"] == "r1" and e["payload"]["row_count"] == 3


def test_sql_is_hashed_not_stored(meta):
    sql = "SELECT region, SUM(net_amt) FROM sales GROUP BY region"
    audit.write_audit_event({"run_id": "r2", "event_type": "execute", "sql": sql})
    e = last()
    assert e["payload"]["sql_sha256"] == audit.sql_hash(sql)
    assert "SELECT" not in str(e) and "net_amt" not in str(e)


def test_unknown_keys_dropped(meta):
    audit.write_audit_event({"run_id": "r3", "event_type": "x",
                             "rows": [["a", 1]], "params": ["secret"],
                             "answer": "full answer text"})
    p = last()["payload"]
    assert "rows" not in p and "params" not in p and "answer" not in p


def test_protected_text_redacted(meta):
    audit.write_audit_event({"run_id": "r4", "event_type": "policy",
                             "reason_code": "salary access", "error_code": "x"})
    assert "salary" not in str(last()).lower()


def test_same_sql_same_hash():
    assert audit.sql_hash("SELECT 1") == audit.sql_hash("  SELECT 1  ")


def test_never_raises_on_bad_input(meta):
    audit.write_audit_event(None)
    audit.write_audit_event("not a dict")
    audit.write_audit_event({"sql": 12345, "run_id": object()})


def test_never_raises_when_db_broken(monkeypatch):
    monkeypatch.setattr(config, "METADATA_DB", "Z:\\no\\such\\dir\\x.sqlite")
    audit.write_audit_event({"run_id": "r5", "event_type": "x"})