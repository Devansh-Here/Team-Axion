"""Deterministic, evidence-oriented business analytics helpers."""

from collections.abc import Mapping
import math


def _finite_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def compare_periods(
    current: float,
    baseline: float,
    *,
    current_label: str = "current",
    baseline_label: str = "baseline",
    current_sample_size: int | None = None,
    baseline_sample_size: int | None = None,
    current_complete: bool = True,
    baseline_complete: bool = True,
    comparable: bool = True,
) -> dict:
    """Compare two like-for-like periods without making causal claims."""
    current_value = _finite_number(current, "current")
    baseline_value = _finite_number(baseline, "baseline")
    if current_sample_size is not None and current_sample_size < 0:
        raise ValueError("current_sample_size must not be negative")
    if baseline_sample_size is not None and baseline_sample_size < 0:
        raise ValueError("baseline_sample_size must not be negative")

    absolute_change = current_value - baseline_value
    warnings = []
    if baseline_value == 0:
        percent_change = None
        warnings.append("ZERO_BASELINE_PERCENT_UNDEFINED")
    else:
        percent_change = (absolute_change / baseline_value) * 100.0
    if not current_complete or not baseline_complete:
        warnings.append("INCOMPLETE_PERIOD")
    if not comparable:
        warnings.append("PERIODS_NOT_LIKE_FOR_LIKE")

    return {
        "type": "period_comparison",
        "current_period": {
            "label": current_label,
            "value": current_value,
            "sample_size": current_sample_size,
            "complete": current_complete,
        },
        "baseline_period": {
            "label": baseline_label,
            "value": baseline_value,
            "sample_size": baseline_sample_size,
            "complete": baseline_complete,
        },
        "absolute_change": absolute_change,
        "percent_change": percent_change,
        "warnings": warnings,
        "interpretation": "Observed change only; this is not a causal conclusion.",
    }


def top_bottom_categories(values: Mapping[str, float], limit: int = 5) -> dict:
    """Return deterministic top and bottom categories from numeric values."""
    if limit < 1:
        raise ValueError("limit must be positive")
    cleaned = [(str(label), _finite_number(value, "category value")) for label, value in values.items()]
    ranked_high = sorted(cleaned, key=lambda item: (-item[1], item[0]))
    ranked_low = sorted(cleaned, key=lambda item: (item[1], item[0]))
    return {
        "top": [{"category": label, "value": value} for label, value in ranked_high[:limit]],
        "bottom": [{"category": label, "value": value} for label, value in ranked_low[:limit]],
    }


def missingness_hotspots(profile: Mapping[str, dict], limit: int = 5) -> list[dict]:
    """Rank columns with the highest observed missingness from profiler output."""
    if limit < 1:
        raise ValueError("limit must be positive")
    hotspots = []
    for table_name, table in profile.items():
        if not isinstance(table, Mapping):
            continue
        row_count = table.get("row_count", 0)
        if not isinstance(row_count, int) or row_count < 0:
            continue
        for column_name, column in table.get("columns", {}).items():
            if not isinstance(column, Mapping):
                continue
            marker_counts = column.get("missing_marker_counts", {})
            marker_total = sum(value for value in marker_counts.values() if isinstance(value, int) and value >= 0)
            missing_count = int(column.get("null_count", 0) or 0) + int(column.get("blank_count", 0) or 0) + marker_total
            rate = (missing_count / row_count * 100.0) if row_count else 0.0
            hotspots.append({
                "table": str(table_name),
                "column": str(column_name),
                "missing_count": missing_count,
                "row_count": row_count,
                "missing_percent": rate,
            })
    return sorted(
        hotspots,
        key=lambda item: (-item["missing_percent"], -item["missing_count"], item["table"], item["column"]),
    )[:limit]
