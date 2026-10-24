import pytest
from fastapi.testclient import TestClient

from app import config, main, metadata_db
from app.contracts import AnalysisOutcome

BASE = "/api/v1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "METADATA_DB", str(tmp_path / "m.sqlite"))
    monkeypatch.setenv("APP_ROLE", "analyst")
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


def fake_analyze(req, role):
    fake_analyze.seen_role = role
    return AnalysisOutcome(run_id="run-1", status="ANSWER", answer="ok")


def test_health(client):
    r = client.get(f"{BASE}/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_datasets_list(client):
    assert client.get(f"{BASE}/datasets").status_code == 200


def test_schema_has_no_salary(client):
    r = client.get(f"{BASE}/datasets/demo/schema")
    assert r.status_code == 200
    assert "salary" not in r.text.lower()
    assert "department" in r.text


def test_schema_unknown_dataset_is_safe_404(client):
    r = client.get(f"{BASE}/datasets/nope/schema")
    assert r.status_code == 404
    assert set(r.json()["error"]) == {"code", "message", "run_id", "retryable"}


def test_analyze_ok_and_run_saved(client, monkeypatch):
    monkeypatch.setattr(main, "analyze", fake_analyze)
    r = client.post(f"{BASE}/analyze", json={"dataset_id": "demo", "question": "sales?"})
    assert r.status_code == 200 and r.json()["run_id"] == "run-1"
    assert client.get(f"{BASE}/runs/run-1").json()["status"] == "ANSWER"
    assert len(client.get(f"{BASE}/audit").json()["events"]) == 1


def test_client_cannot_choose_role(client, monkeypatch):
    monkeypatch.setattr(main, "analyze", fake_analyze)
    client.post(f"{BASE}/analyze",
                json={"dataset_id": "demo", "question": "q", "role": "admin"})
    assert fake_analyze.seen_role == "analyst"


@pytest.mark.parametrize("q", ["", "   ", "x" * 2001])
def test_bad_question_rejected(client, q):
    r = client.post(f"{BASE}/analyze", json={"dataset_id": "demo", "question": q})
    assert r.status_code == 422
    assert "error" in r.json()


def test_missing_fields_safe_422(client):
    r = client.post(f"{BASE}/analyze", json={})
    assert r.status_code == 422 and "error" in r.json()


def test_unknown_run_404(client):
    r = client.get(f"{BASE}/runs/zzz")
    assert r.status_code == 404 and r.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_evidence_roundtrip_and_salary_stripped(client):
    metadata_db.save_evidence("e1", "run-9", {"sql": "SELECT 1", "salary": 999,
                                               "nested": {"employees.salary": 5}})
    r = client.get(f"{BASE}/runs/run-9/evidence")
    assert r.status_code == 200 and r.json()["sql"] == "SELECT 1"
    assert "salary" not in r.text.lower()


def test_internal_error_leaks_nothing(client, monkeypatch):
    def boom(req, role):
        raise RuntimeError("secret C:\\Users\\Kartik\\hidden.db Traceback")
    monkeypatch.setattr(main, "analyze", boom)
    r = client.post(f"{BASE}/analyze", json={"dataset_id": "demo", "question": "q"})
    assert r.status_code == 500
    for bad in ("secret", "Traceback", "hidden", "C:\\"):
        assert bad not in r.text
    assert r.json()["error"]["retryable"] is True


def test_audit_limit_validated(client):
    assert client.get(f"{BASE}/audit?limit=100000").status_code == 422