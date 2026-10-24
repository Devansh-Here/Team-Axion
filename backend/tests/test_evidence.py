from app.evidence import ALLOWED_KEYS, build_evidence_pack, make_evidence_saver
from app.prompts import PROMPT_VERSION

TRACE = {
    "run_id": "run_1", "dataset_id": "demo", "question": "Total net sales", "status": "ANSWER",
    "policy_action": "ALLOW", "schema_hash": "abc", "sql": "SELECT 1", "assumptions": ["calendar year"],
    "checks": [], "warnings": [], "attempts": 2, "rejections": ["no_such_column"],
    "result_summary": {"columns": ["t"], "rows": [[1]], "row_count": 1, "truncated": False, "extra": "x"},
    "secret_internal": "must not be stored",
}


def test_pack_contains_required_fields():
    p = build_evidence_pack(TRACE, "ev_1", "m1")
    assert p["evidence_id"] == "ev_1" and p["run_id"] == "run_1"
    assert p["model"] == {"name": "m1", "prompt_version": PROMPT_VERSION}
    assert p["repair_attempts"] == 1
    assert p["parameters"] == []
    assert p["dataset_sha256"] == "TBD"


def test_unknown_keys_are_dropped():
    p = build_evidence_pack(TRACE, "ev_1", "m1")
    assert "secret_internal" not in p
    assert "extra" not in p["result_summary"]


def test_pack_has_no_sql_when_trace_has_none():
    t = {k: v for k, v in TRACE.items() if k != "sql"}
    assert "sql" not in build_evidence_pack(t, "ev_1", "m1")


def test_saver_calls_store_with_expected_args_and_returns_id():
    calls = []
    save = make_evidence_saver(lambda eid, rid, payload: calls.append((eid, rid, payload)), "m1")
    eid = save(dict(TRACE))
    assert eid.startswith("ev_")
    assert calls[0][0] == eid and calls[0][1] == "run_1"
    assert calls[0][2]["evidence_id"] == eid


def test_all_pack_keys_are_whitelisted_or_added_fields():
    p = build_evidence_pack(TRACE, "ev_1", "m1")
    added = {"evidence_id", "parameters", "dataset_sha256", "model", "repair_attempts"}
    assert set(p) <= set(ALLOWED_KEYS) | added