import pytest

from app.analytics import compare_periods, missingness_hotspots, top_bottom_categories


def test_compare_periods_reports_absolute_and_percent_change():
    result = compare_periods(
        125_000,
        100_000,
        current_label="2025",
        baseline_label="2024",
        current_sample_size=120,
        baseline_sample_size=110,
    )

    assert result["absolute_change"] == 25_000.0
    assert result["percent_change"] == 25.0
    assert result["current_period"]["sample_size"] == 120
    assert result["warnings"] == []
    assert "causal" in result["interpretation"]


def test_compare_periods_zero_baseline_is_undefined():
    result = compare_periods(100, 0)

    assert result["absolute_change"] == 100.0
    assert result["percent_change"] is None
    assert result["warnings"] == ["ZERO_BASELINE_PERCENT_UNDEFINED"]


def test_compare_periods_flags_incomplete_and_non_comparable_periods():
    result = compare_periods(90, 100, current_complete=False, comparable=False)

    assert result["warnings"] == ["INCOMPLETE_PERIOD", "PERIODS_NOT_LIKE_FOR_LIKE"]


def test_compare_periods_rejects_non_finite_values():
    with pytest.raises(ValueError):
        compare_periods(float("nan"), 10)


def test_top_bottom_categories_are_deterministic():
    result = top_bottom_categories({"B": 10, "A": 10, "C": -2}, limit=2)

    assert result["top"] == [{"category": "A", "value": 10.0}, {"category": "B", "value": 10.0}]
    assert result["bottom"] == [{"category": "C", "value": -2.0}, {"category": "A", "value": 10.0}]


def test_missingness_hotspots_rank_profile_columns():
    profile = {
        "sales": {
            "row_count": 10,
            "columns": {
                "region": {"null_count": 1, "blank_count": 1, "missing_marker_counts": {"N/A": 2}},
                "net_amt": {"null_count": 0, "blank_count": 0, "missing_marker_counts": {"N/A": 0}},
            },
        }
    }

    result = missingness_hotspots(profile)

    assert result[0] == {
        "table": "sales",
        "column": "region",
        "missing_count": 4,
        "row_count": 10,
        "missing_percent": 40.0,
    }


def test_invalid_limit_is_rejected():
    with pytest.raises(ValueError):
        top_bottom_categories({"A": 1}, limit=0)
    with pytest.raises(ValueError):
        missingness_hotspots({}, limit=0)
