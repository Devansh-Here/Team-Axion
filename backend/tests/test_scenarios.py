import pytest

from app.scenarios import calculate_scenario, validate_scenario_inputs


def test_calculate_scenario_returns_low_base_high_and_sensitivity():
    result = calculate_scenario(
        100_000,
        2,
        3,
        4,
        assumption_name="revenue per spend",
        units="x",
        baseline_evidence_id="ev-1",
    )

    assert result["outputs"] == {"low": 200_000.0, "base": 300_000.0, "high": 400_000.0}
    assert result["baseline"]["evidence_id"] == "ev-1"
    assert result["sensitivity"]["output_change_per_one_assumption_unit"] == 100_000.0
    assert "ASSUMPTION_ONLY" in result["warnings"]
    assert "causal" in result["interpretation"]


def test_scenario_rejects_failed_or_truncated_baseline():
    with pytest.raises(ValueError, match="did not complete"):
        calculate_scenario(100, 1, 2, 3, baseline_status="ERROR")
    with pytest.raises(ValueError, match="truncated"):
        calculate_scenario(100, 1, 2, 3, baseline_truncated=True)


def test_scenario_enforces_order_and_bounds():
    with pytest.raises(ValueError, match="ordered"):
        calculate_scenario(100, 3, 2, 4)
    with pytest.raises(ValueError, match="maximum"):
        calculate_scenario(100, 1, 2, 4, maximum_assumption=3)


def test_scenario_rejects_non_finite_values():
    with pytest.raises(ValueError):
        calculate_scenario(float("inf"), 1, 2, 3)


def test_validate_scenario_inputs_returns_normalized_values():
    result = validate_scenario_inputs({"low": 2, "base": 3}, minimum=1, maximum=4)

    assert result == {"low": 2.0, "base": 3.0}


def test_validate_scenario_inputs_requires_non_empty_mapping():
    with pytest.raises(ValueError):
        validate_scenario_inputs({})
