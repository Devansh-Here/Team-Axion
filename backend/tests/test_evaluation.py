import json

from app.evaluation import load_cases, render_results_markdown, run_evaluation


def test_load_cases_requires_unique_ids(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([
        {"id": "a", "question": "one"},
        {"id": "b", "question": "two"},
    ]), encoding="utf-8")

    cases = load_cases(path)

    assert [case["id"] for case in cases] == ["a", "b"]


def test_run_evaluation_computes_only_explicit_metrics():
    cases = [
        {"id": "b", "question": "two"},
        {"id": "a", "question": "one"},
    ]

    def runner(case):
        if case["id"] == "a":
            return {
                "correct": True,
                "valid_sql": True,
                "repair_eligible": True,
                "repair_success": True,
                "expected_unanswerable": False,
                "abstained": False,
                "latency_ms": 10,
            }
        return {
            "correct": False,
            "valid_sql": True,
            "repair_eligible": False,
            "expected_unanswerable": True,
            "abstained": True,
            "latency_ms": 20,
        }

    summary = run_evaluation(cases, runner, seed=7)

    assert summary["case_count"] == 2
    assert summary["metrics"]["execution_accuracy"] == 0.5
    assert summary["metrics"]["valid_sql_rate"] == 1.0
    assert summary["metrics"]["repair_success"] == 1.0
    assert summary["metrics"]["abstention_precision"] == 1.0
    assert summary["metrics"]["abstention_recall"] == 1.0
    assert summary["metrics"]["median_latency_ms"] == 15


def test_unmeasured_metrics_stay_tbd():
    summary = run_evaluation([{"id": "a", "question": "one"}], lambda case: {"status": "ANSWER"})

    report = render_results_markdown(summary)

    assert summary["metrics"]["execution_accuracy"] is None
    assert "TBD / NOT RUN" in report
