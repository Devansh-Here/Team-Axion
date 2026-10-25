from fastapi.testclient import TestClient

from app import config, main, metadata_db
from app.contracts import AnalysisOutcome


def test_three_turn_follow_up_context_is_sent_to_agent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "METADATA_DB", str(tmp_path / "metadata.sqlite"))
    seen = []

    def fake(req, role):
        seen.append(req.question)
        return AnalysisOutcome(run_id=f"run-{len(seen)}", status="ANSWER", answer="ok")

    monkeypatch.setattr(main, "analyze", fake)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        first = client.post("/api/v1/analyze", json={
            "dataset_id": "demo", "question": "Total net sales by region in 2025",
            "conversation_id": "conv-phase2",
        })
        second = client.post("/api/v1/analyze", json={
            "dataset_id": "demo", "question": "Now only for Delhi",
            "conversation_id": "conv-phase2",
        })
        third = client.post("/api/v1/analyze", json={
            "dataset_id": "demo", "question": "Now only for 2023",
            "conversation_id": "conv-phase2",
        })
    assert [first.status_code, second.status_code, third.status_code] == [200, 200, 200]
    assert "2025" in seen[0]
    assert "Total net sales by region in 2025" in seen[1] and "Delhi" in seen[1]
    assert "Delhi" in seen[2] and "2023" in seen[2] and "2025" in seen[2]
    assert metadata_db.list_conversation_questions("conv-phase2", path=str(tmp_path / "metadata.sqlite")) == [
        "Total net sales by region in 2025", "Now only for Delhi", "Now only for 2023"
    ]
