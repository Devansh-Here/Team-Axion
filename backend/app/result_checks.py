"""Deterministic checks applied after a guarded query executes."""

import math
import re

from app.contracts import QueryOutcome, ValidationReport


_AGGREGATE_RE = re.compile(r"\b(count|sum|avg|min|max)\s*\(", re.IGNORECASE)
_TEMPORAL_RE = re.compile(
    r"\b(trend|over time|compared?|comparison|declin|falling|last year|year[- ]over[- ]year|quarter|month)\b",
    re.IGNORECASE,
)
_JOIN_RE = re.compile(r"\bjoin\b", re.IGNORECASE)


def _check(checks: list[dict], code: str, status: str, detail: str) -> None:
    checks.append({"code": code, "status": status, "detail": detail})


def _profile_has_warning(profile: dict, warning: str) -> bool:
    for table in profile.values() if isinstance(profile, dict) else []:
        if not isinstance(table, dict):
            continue
        for column in table.get("columns", {}).values():
            if warning in column.get("warnings", []):
                return True
    return False


def _profile_has_duplicate_rows(profile: dict) -> bool:
    for table in profile.values() if isinstance(profile, dict) else []:
        if isinstance(table, dict) and table.get("duplicate_like_rows", 0) > 0:
            return True
    return False


def _has_non_finite(rows: list[list]) -> bool:
    for row in rows:
        for value in row:
            if isinstance(value, float) and not math.isfinite(value):
                return True
    return False


def validate_result(question: str, sql: str, outcome: QueryOutcome, profile: dict) -> ValidationReport:
    """Return PASS/WARNING/BLOCKED checks without inventing numeric facts."""
    checks: list[dict] = []
    warnings: list[str] = []
    needs_clarification = False
    blocked = False

    if not isinstance(outcome, QueryOutcome):
        _check(checks, "OUTCOME_SHAPE", "BLOCKED", "Query outcome is invalid.")
        return ValidationReport(acceptable=False, checks=checks, warnings=["INVALID_OUTCOME"])

    if outcome.status != "OK":
        _check(checks, "EXECUTION_STATUS", "BLOCKED", "The query did not complete successfully.")
        return ValidationReport(
            acceptable=False,
            checks=checks,
            warnings=[outcome.error_code or "QUERY_NOT_OK"],
        )
    _check(checks, "EXECUTION_STATUS", "PASS", "Query completed successfully.")

    if outcome.row_count < 0 or len(outcome.rows) > outcome.row_count:
        _check(checks, "RESULT_SHAPE", "BLOCKED", "Result row metadata is inconsistent.")
        blocked = True
    elif any(len(row) != len(outcome.columns) for row in outcome.rows):
        _check(checks, "RESULT_SHAPE", "BLOCKED", "Result rows do not match the reported columns.")
        blocked = True
    else:
        _check(checks, "RESULT_SHAPE", "PASS", "Rows match the reported result columns.")

    if _has_non_finite(outcome.rows):
        _check(checks, "NON_FINITE_NUMBERS", "BLOCKED", "Result contains a non-finite numeric value.")
        warnings.append("NON_FINITE_NUMBERS")
        blocked = True
    else:
        _check(checks, "NON_FINITE_NUMBERS", "PASS", "No non-finite numeric values found.")

    if outcome.row_count == 0:
        _check(checks, "EMPTY_RESULT", "WARNING", "No rows matched the current filters.")
        warnings.append("NO_ROWS_MATCHED")
    elif outcome.rows and all(value is None for row in outcome.rows for value in row):
        _check(checks, "ALL_NULL_RESULT", "BLOCKED", "Result contains no observed values; zero must not be inferred.")
        warnings.append("ALL_NULL_RESULT")
        blocked = True
    else:
        _check(checks, "NULL_SEMANTICS", "PASS", "Result contains at least one observed value.")

    if outcome.truncated:
        detail = "Result was truncated; totals must not be computed from the preview."
        status = "BLOCKED" if _AGGREGATE_RE.search(sql or "") else "WARNING"
        _check(checks, "TRUNCATED_RESULT", status, detail)
        warnings.append("RESULT_TRUNCATED")
        blocked = blocked or status == "BLOCKED"
    else:
        _check(checks, "TRUNCATED_RESULT", "PASS", "Result was not truncated.")

    if _TEMPORAL_RE.search(question or ""):
        if _profile_has_warning(profile, "AMBIGUOUS_DATES"):
            _check(checks, "TEMPORAL_COMPARABILITY", "WARNING", "Date values are ambiguous for a period comparison.")
            warnings.append("AMBIGUOUS_DATES")
            needs_clarification = True
        else:
            _check(checks, "TEMPORAL_COMPARABILITY", "PASS", "No ambiguous date warning was found in the profile.")

    if _JOIN_RE.search(sql or "") and _profile_has_duplicate_rows(profile):
        _check(checks, "JOIN_INFLATION", "WARNING", "Duplicate-like source rows may multiply joined results.")
        warnings.append("JOIN_INFLATION_RISK")

    return ValidationReport(
        acceptable=not blocked and not needs_clarification,
        checks=checks,
        warnings=warnings,
        needs_clarification=needs_clarification,
    )
