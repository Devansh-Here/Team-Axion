"""Result checks (Lane B). Mechanical checks only; never claims semantic certainty."""
import math
import re

from app.contracts import QueryOutcome, ValidationReport


def _check(code, status, detail):
    return {"code": code, "status": status, "detail": detail}


def _used_columns(sql, profile):
    """(table, column, info) for profiled columns whose table AND column name appear in the SQL."""
    out = []
    for table, cols in (profile or {}).items():
        if not isinstance(cols, dict) or not re.search(rf"\b{re.escape(table)}\b", sql, re.I):
            continue
        for col, info in cols.items():
            if col == "__table__" or not isinstance(info, dict):
                continue
            if re.search(rf"\b{re.escape(col)}\b", sql, re.I):
                out.append((table, col, info))
    return out


def _join_inflation_risk(sql: str) -> bool:
    """Detect the CRM's known one-to-many deal/contact aggregation hazard.

    This is a conservative warning, not a claim that every join is wrong. A
    query that aggregates deal values after joining contacts should either
    pre-aggregate deals or use a distinct/grain-safe strategy.
    """
    has_deals = re.search(r"\b(?:from|join)\s+(?:main\.)?deals\b", sql, re.I)
    has_contacts = re.search(r"\bjoin\s+(?:main\.)?contacts\b", sql, re.I)
    has_aggregate = re.search(r"\b(sum|avg|count)\s*\(", sql, re.I)
    return bool(has_deals and has_contacts and has_aggregate)


def _dirty_numeric_aggregation(sql: str, profile: dict) -> list[tuple[str, str, dict]]:
    """Return dirty text columns used for unsafe numeric aggregation/ranking."""
    has_numeric_aggregate = re.search(r"\b(?:sum|avg|max|min)\s*\(", sql, re.I)
    has_order_by = re.search(r"\border\s+by\b", sql, re.I)
    if not has_numeric_aggregate and not has_order_by:
        return []
    dirty = []
    for table, col, info in _used_columns(sql, profile):
        order_uses_column = re.search(
            rf"\border\s+by\b[^;]*\b{re.escape(col)}\b", sql, re.I
        )
        aggregate_uses_column = re.search(
            rf"\b(?:sum|avg|max|min)\s*\([^)]*\b{re.escape(col)}\b",
            sql,
            re.I,
        )
        if (
            info.get("type") == "text"
            and (aggregate_uses_column or order_uses_column)
            and (info.get("blank") or info.get("missing_marker") or info.get("warnings"))
        ):
            dirty.append((table, col, info))
    return dirty


def validate_result(question: str, sql: str, outcome: QueryOutcome, profile: dict) -> ValidationReport:
    checks, warnings = [], []

    if outcome.status != "OK":
        checks.append(_check("EXECUTION_NOT_OK", "BLOCKED", "Query did not complete successfully."))
        return ValidationReport(acceptable=False, checks=checks, warnings=warnings)

    rows = outcome.rows or []

    if not rows:
        w = "No rows matched the current filters."  # not proof the entity does not exist
        checks.append(_check("EMPTY_RESULT", "WARNING", w))
        warnings.append(w)
    else:
        cells = [v for r in rows for v in r]
        if all(v is None for v in cells):
            checks.append(_check("ALL_NULL", "BLOCKED", "Every returned value is NULL; no zero is invented."))
            return ValidationReport(acceptable=False, checks=checks, warnings=warnings)
        if any(isinstance(v, float) and not math.isfinite(v) for v in cells):
            checks.append(_check("NON_FINITE", "BLOCKED", "Result contains NaN or infinity."))
            return ValidationReport(acceptable=False, checks=checks, warnings=warnings)
        checks.append(_check("RESULT_SHAPE", "PASS", f"{len(rows)} row(s) returned."))

    if outcome.truncated:
        w = "Result was truncated at the row/byte cap; do not total it."
        checks.append(_check("TRUNCATED", "WARNING", w))
        warnings.append(w)

    if _join_inflation_risk(sql):
        w = (
            "Potential join inflation: deals are aggregated after joining contacts; "
            "pre-aggregate at deal grain or use a distinct-safe calculation."
        )
        checks.append(_check("JOIN_INFLATION_RISK", "WARNING", w))
        warnings.append(w)

    dirty_numeric = _dirty_numeric_aggregation(sql, profile)
    if dirty_numeric:
        columns = ", ".join(f"{table}.{col}" for table, col, _ in dirty_numeric)
        w = (
            f"Numeric aggregation blocked for {columns}: values contain blanks, "
            "missing markers, or non-canonical text formats."
        )
        checks.append(_check("DIRTY_NUMERIC_AGGREGATION", "BLOCKED", w))
        warnings.append(w)
        return ValidationReport(acceptable=False, checks=checks, warnings=warnings)

    for table, col, info in _used_columns(sql, profile):
        missing = (info.get("blank") or 0) + (info.get("missing_marker") or 0)
        if missing:
            w = f"{table}.{col} has {missing} blank/missing-marker values that are not real data."
            checks.append(_check("MISSING_MARKERS", "WARNING", w))
            warnings.append(w)
        if info.get("ambiguous"):
            w = f"{table}.{col} has {info['ambiguous']} ambiguous dates (dd/mm vs mm/dd)."
            checks.append(_check("AMBIGUOUS_DATES", "WARNING", w))
            warnings.append(w)
        if info.get("unparseable"):
            w = f"{table}.{col} has {info['unparseable']} unparseable dates; period filters may skip them."
            checks.append(_check("UNPARSEABLE_DATES", "WARNING", w))
            warnings.append(w)
        if info.get("mixed_precision"):
            w = f"{table}.{col} mixes full dates and year-only values."
            checks.append(_check("MIXED_DATE_PRECISION", "WARNING", w))
            warnings.append(w)

    return ValidationReport(acceptable=True, checks=checks, warnings=warnings)
