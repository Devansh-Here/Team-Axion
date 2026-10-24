"""Read-only SQLite profiling helpers for the data-quality lane.

The profiler deliberately returns statistics, not sample cell values.  Callers
must pass the policy-filtered table list, and this module never mutates the
source connection.
"""

from collections import Counter
from datetime import date, datetime
import math
import re
import sqlite3


MISSING_MARKERS = ("N/A", "NA", "-", "unknown")
_YEAR_RE = re.compile(r"^\d{4}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_SLASH_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


def _quote_identifier(identifier: str) -> str:
    if not isinstance(identifier, str) or not identifier:
        raise ValueError("invalid table name")
    return '"' + identifier.replace('"', '""') + '"'


def _normalise_text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_missing(value) -> bool:
    if value is None:
        return True
    text = _normalise_text(value)
    return text == "" or text.casefold() in {marker.casefold() for marker in MISSING_MARKERS}


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _parse_date(value):
    """Return (parsed date, ambiguous) for the small supported date grammar."""
    if isinstance(value, datetime):
        return value.date(), False
    if isinstance(value, date):
        return value, False
    if not isinstance(value, str):
        return None, False
    text = value.strip()
    if _YEAR_RE.fullmatch(text):
        return date(int(text), 1, 1), False
    if _ISO_DATE_RE.fullmatch(text):
        try:
            return datetime.strptime(text, "%Y-%m-%d").date(), False
        except ValueError:
            return None, False
    if _SLASH_DATE_RE.fullmatch(text):
        first, second, year = (int(part) for part in text.split("/"))
        if first <= 12 and second <= 12 and first != second:
            return None, True
        try:
            if first > 12:
                return date(year, second, first), False
            return date(year, first, second), False
        except ValueError:
            return None, False
    return None, False


def _date_stats(column_name: str, values: list) -> dict:
    candidate = "date" in column_name.lower() or "time" in column_name.lower() or "year" in column_name.lower()
    if not candidate:
        return {"min": None, "max": None, "ambiguous_count": 0}
    parsed = []
    ambiguous_count = 0
    for value in values:
        parsed_value, ambiguous = _parse_date(value)
        ambiguous_count += int(ambiguous)
        if parsed_value is not None:
            parsed.append(parsed_value)
    return {
        "min": min(parsed).isoformat() if parsed else None,
        "max": max(parsed).isoformat() if parsed else None,
        "ambiguous_count": ambiguous_count,
    }


def _inferred_type(declared_type: str, values: list) -> str:
    nonmissing = [value for value in values if not _is_missing(value)]
    if not nonmissing:
        return "unknown"
    if all(_number(value) is not None for value in nonmissing):
        return "number"
    if all(_parse_date(value)[0] is not None for value in nonmissing):
        return "date"
    declared = (declared_type or "").upper()
    if any(token in declared for token in ("INT", "REAL", "NUM", "DEC", "FLOAT", "DOUBLE")):
        return "mixed" if any(_number(value) is None for value in nonmissing) else "number"
    return "text"


def _column_profile(name: str, declared_type: str, values: list) -> dict:
    null_count = sum(value is None for value in values)
    blank_count = sum(isinstance(value, str) and value.strip() == "" for value in values)
    marker_counts = {
        marker: sum(isinstance(value, str) and value.strip().lower() == marker.lower() for value in values)
        for marker in MISSING_MARKERS
    }
    nonnull = [value for value in values if value is not None]
    distinct_count = len({repr(value) for value in nonnull})
    numeric_values = [number for value in values if (number := _number(value)) is not None]
    dates = _date_stats(name, values)
    inferred = _inferred_type(declared_type, values)
    warnings = []
    if null_count or blank_count or any(marker_counts.values()):
        warnings.append("MISSING_VALUES")
    if inferred == "mixed":
        warnings.append("MIXED_TYPES")
    if dates["ambiguous_count"]:
        warnings.append("AMBIGUOUS_DATES")
    if distinct_count <= 1 and values:
        warnings.append("CONSTANT_COLUMN")
    return {
        "declared_type": declared_type or "",
        "inferred_type": inferred,
        "null_count": null_count,
        "blank_count": blank_count,
        "missing_marker_counts": marker_counts,
        "distinct_count": distinct_count,
        "numeric_range": {
            "min": min(numeric_values) if numeric_values else None,
            "max": max(numeric_values) if numeric_values else None,
        },
        "date_range": dates,
        "warnings": warnings,
    }


def profile_columns(conn: sqlite3.Connection, tables: list[str]) -> dict:
    """Return deterministic, policy-filterable profile statistics for tables."""
    if conn is None or not hasattr(conn, "execute"):
        raise TypeError("conn must be a SQLite connection")

    result = {}
    for table in tables:
        quoted_table = _quote_identifier(table)
        table_info = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
        if not table_info:
            raise ValueError("table not found")
        names = [row[1] for row in table_info]
        declared = {row[1]: row[2] or "" for row in table_info}
        values_by_column = {name: [] for name in names}
        row_counter = Counter()
        row_count = 0
        cursor = conn.execute(f"SELECT * FROM {quoted_table}")
        for row in cursor:
            row_count += 1
            row_counter[tuple(repr(value) for value in row)] += 1
            for index, name in enumerate(names):
                values_by_column[name].append(row[index])

        columns = {
            name: _column_profile(name, declared[name], values_by_column[name])
            for name in names
        }
        duplicate_like_rows = sum(count - 1 for count in row_counter.values() if count > 1)
        result[table] = {
            "row_count": row_count,
            "column_count": len(names),
            "duplicate_like_rows": duplicate_like_rows,
            "columns": columns,
        }
    return result
