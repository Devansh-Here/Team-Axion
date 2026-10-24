import sqlite3

from app.contracts import AnalysisRequest
from app.agent import analyze
from app.policy import authorize


def test_stubs_wire_together():
    out = analyze(AnalysisRequest(dataset_id="d", question="q"), role="analyst")
    assert out.run_id
    assert authorize("analyst", "d", "q").action == "ALLOW"


def test_demo_db_has_messy_rows(demo_db):
    conn = sqlite3.connect(demo_db)
    count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    conn.close()
    assert count == 4