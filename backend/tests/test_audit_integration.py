from app.audit import sanitize_event


def test_agent_style_event_stores_hash_not_sql():
    event = {"run_id": "run_1", "event_type": "analysis", "dataset_id": "demo", "status": "ANSWER",
             "policy_action": "ALLOW", "row_count": 3, "repair_attempts": 0, "error_code": None,
             "sql": "SELECT category, SUM(net_amt) FROM sales GROUP BY category"}
    clean = sanitize_event(event)
    assert "sql" not in clean
    assert len(clean["sql_sha256"]) == 64
    assert clean["status"] == "ANSWER"
    assert clean["repair_attempts"] == 0