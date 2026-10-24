"""Bounded, deterministic what-if calculations with explicit assumptions."""

import math
from collections.abc import Mapping


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def calculate_scenario(
    baseline_value: float,
    low_assumption: float,
    base_assumption: float,
    high_assumption: float,
    *,
    assumption_name: str = "assumption",
    baseline_label: str = "baseline",
    units: str = "x",
    baseline_evidence_id: str | None = None,
    baseline_truncated: bool = False,
    baseline_status: str = "OK",
    minimum_assumption: float | None = None,
    maximum_assumption: float | None = None,
    scenario_type: str = "assumption_only_estimate",
) -> dict:
    """Calculate low/base/high outputs as baseline × assumption.

    This is arithmetic under an explicit assumption. It never writes source
    data and refuses to calculate from a failed or truncated baseline.
    """
    baseline = _finite(baseline_value, "baseline_value")
    assumptions = {
        "low": _finite(low_assumption, "low_assumption"),
        "base": _finite(base_assumption, "base_assumption"),
        "high": _finite(high_assumption, "high_assumption"),
    }
    if baseline_status != "OK":
        raise ValueError("baseline query did not complete successfully")
    if baseline_truncated:
        raise ValueError("baseline result is truncated")
    if minimum_assumption is not None:
        minimum = _finite(minimum_assumption, "minimum_assumption")
        if any(value < minimum for value in assumptions.values()):
            raise ValueError("assumption is below the permitted minimum")
    if maximum_assumption is not None:
        maximum = _finite(maximum_assumption, "maximum_assumption")
        if any(value > maximum for value in assumptions.values()):
            raise ValueError("assumption exceeds the permitted maximum")
    if not assumptions["low"] <= assumptions["base"] <= assumptions["high"]:
        raise ValueError("assumptions must be ordered low <= base <= high")

    outputs = {name: baseline * value for name, value in assumptions.items()}
    sensitivity = {
        "formula": "baseline_value × assumption",
        "output_change_per_one_assumption_unit": baseline,
    }
    return {
        "type": "scenario",
        "classification": scenario_type,
        "baseline": {
            "label": baseline_label,
            "value": baseline,
            "evidence_id": baseline_evidence_id,
        },
        "assumption": {
            "name": assumption_name,
            "units": units,
            "low": assumptions["low"],
            "base": assumptions["base"],
            "high": assumptions["high"],
        },
        "outputs": outputs,
        "sensitivity": sensitivity,
        "warnings": ["ASSUMPTION_ONLY", "NOT_A_CAUSAL_FORECAST"],
        "interpretation": "Under these assumptions, the calculated outputs are arithmetic scenarios; they are not promises or causal forecasts.",
    }


def validate_scenario_inputs(inputs: Mapping[str, float], *, minimum: float | None = None, maximum: float | None = None) -> dict:
    """Validate a named assumption map for a UI before calculation."""
    if not isinstance(inputs, Mapping) or not inputs:
        raise ValueError("at least one assumption is required")
    values = {str(name): _finite(value, str(name)) for name, value in inputs.items()}
    if minimum is not None and any(value < _finite(minimum, "minimum") for value in values.values()):
        raise ValueError("assumption is below the permitted minimum")
    if maximum is not None and any(value > _finite(maximum, "maximum") for value in values.values()):
        raise ValueError("assumption exceeds the permitted maximum")
    return values
