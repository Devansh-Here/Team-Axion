"""Small deterministic evaluation harness; it never invents missing metrics."""

from collections.abc import Callable, Iterable, Mapping
import json
from pathlib import Path
import statistics
from typing import Any


def load_cases(path: str | Path) -> list[dict]:
    """Load a fixed JSON case list and validate the required fields."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("evaluation cases must be a JSON list")
    cases = []
    seen = set()
    for case in payload:
        if not isinstance(case, Mapping) or not isinstance(case.get("id"), str) or not isinstance(case.get("question"), str):
            raise ValueError("each evaluation case needs id and question")
        if case["id"] in seen:
            raise ValueError("evaluation case IDs must be unique")
        seen.add(case["id"])
        cases.append(dict(case))
    return cases


def _value(result: Any, key: str, default=None):
    if isinstance(result, Mapping):
        return result.get(key, default)
    return getattr(result, key, default)


def _rate(numerator: int, denominator: int):
    return numerator / denominator if denominator else None


def _percentile(values: list[float], percentile: float):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def run_evaluation(cases: Iterable[Mapping], runner: Callable[[Mapping], Any], *, seed: int = 2026) -> dict:
    """Run cases and compute only metrics explicitly supplied by the runner.

    A runner may return ``correct``, ``valid_sql``, ``repair_success``,
    ``repair_eligible``, ``expected_unanswerable``, ``abstained`` and
    ``latency_ms`` fields. Missing fields stay unmeasured instead of being
    inferred from a status string.
    """
    ordered_cases = sorted((dict(case) for case in cases), key=lambda case: case["id"])
    records = []
    for case in ordered_cases:
        try:
            result = runner(case)
            records.append({"id": case["id"], "result": result, "error": None})
        except Exception as exc:
            records.append({"id": case["id"], "result": None, "error": type(exc).__name__})

    explicit_correct = [_value(record["result"], "correct") for record in records if record["result"] is not None]
    valid_sql = [_value(record["result"], "valid_sql") for record in records if record["result"] is not None]
    repair_records = [record["result"] for record in records if record["result"] is not None and _value(record["result"], "repair_eligible") is True]
    latencies = [_value(record["result"], "latency_ms") for record in records if record["result"] is not None]
    latencies = [float(value) for value in latencies if isinstance(value, (int, float)) and value >= 0]

    abstention_rows = [record["result"] for record in records if record["result"] is not None and _value(record["result"], "expected_unanswerable") is not None]
    true_positive = sum(_value(row, "expected_unanswerable") is True and _value(row, "abstained") is True for row in abstention_rows)
    false_positive = sum(_value(row, "expected_unanswerable") is False and _value(row, "abstained") is True for row in abstention_rows)
    false_negative = sum(_value(row, "expected_unanswerable") is True and _value(row, "abstained") is False for row in abstention_rows)

    repair_successes = sum(_value(row, "repair_success") is True for row in repair_records)
    repair_measured = sum(_value(row, "repair_success") is not None for row in repair_records)
    correct_measured = sum(value is not None for value in explicit_correct)
    valid_sql_measured = sum(value is not None for value in valid_sql)
    return {
        "seed": seed,
        "case_count": len(ordered_cases),
        "completed_count": sum(record["result"] is not None for record in records),
        "error_count": sum(record["error"] is not None for record in records),
        "metrics": {
            "execution_accuracy": _rate(sum(value is True for value in explicit_correct), correct_measured),
            "valid_sql_rate": _rate(sum(value is True for value in valid_sql), valid_sql_measured),
            "repair_success": _rate(repair_successes, repair_measured),
            "abstention_precision": _rate(true_positive, true_positive + false_positive),
            "abstention_recall": _rate(true_positive, true_positive + false_negative),
            "median_latency_ms": statistics.median(latencies) if latencies else None,
            "p95_latency_ms": _percentile(latencies, 0.95),
        },
        "records": records,
    }


def render_results_markdown(summary: Mapping, *, hardware: str = "TBD", model: str = "TBD") -> str:
    """Render a truthful report; unmeasured metrics are explicitly TBD."""
    metrics = summary.get("metrics", {})

    def display(value):
        return "TBD / NOT RUN" if value is None else str(value)

    return f"""# Evaluation results

## Status

This report records the evaluation protocol and measured outputs only. No hosted model or fabricated benchmark result is used.

| Field | Value |
|---|---|
| Case count | {summary.get('case_count', 'TBD')} |
| Completed runs | {summary.get('completed_count', 'TBD')} |
| Errors | {summary.get('error_count', 'TBD')} |
| Fixed seed | {summary.get('seed', 'TBD')} |
| Hardware | {hardware} |
| Model/checkpoint | {model} |

## Metrics

| Metric | Result |
|---|---|
| Execution accuracy | {display(metrics.get('execution_accuracy'))} |
| Valid-SQL rate | {display(metrics.get('valid_sql_rate'))} |
| Repair success | {display(metrics.get('repair_success'))} |
| Abstention precision | {display(metrics.get('abstention_precision'))} |
| Abstention recall | {display(metrics.get('abstention_recall'))} |
| Median latency (ms) | {display(metrics.get('median_latency_ms'))} |
| P95 latency (ms) | {display(metrics.get('p95_latency_ms'))} |

## Protocol and limitations

- The current repository contains a fixed synthetic smoke set, not a completed 50–100 question benchmark.
- Full evaluation with the real local model is **TBD / NOT RUN**.
- Tuning and held-out evaluation splits are not yet populated.
- SQL validity, execution success, semantic correctness, abstention quality and latency must be reported separately.
"""
