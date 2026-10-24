"""Profiler (Lane B). Read-only: only SELECT / sqlite_master. Never mutates data."""
import datetime
import math
import re

MISSING_MARKERS = {"n/a", "na", "-", "unknown"}
_YEAR = re.compile(r"^\d{4}$")
_SLASH = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _is_num(s: str) -> bool:
    try:
        return math.isfinite(float(s))
    except ValueError:
        return False


def _parse_date(s: str):
    """Return (norm, ambiguous) or None. norm is 'YYYY-MM-DD' or 'YYYY'."""
    try:
        d = datetime.date.fromisoformat(s[:10])
        return d.isoformat(), False
    except ValueError:
        pass
    if _YEAR.match(s) and 1900 <= int(s) <= 2100:
        return s, False
    m = _SLASH.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a > 12 and b <= 12:
            return y, False
        if b > 12 and a <= 12:
            return y, False
        if a <= 12 and b <= 12:
            return y, a != b  # 04/01 could be dd/mm or mm/dd
    return None


def _profile_column(conn, table, col):
    vals = [r[0] for r in conn.execute(f"SELECT {_q(col)} FROM {_q(table)}")]
    nulls = blank = marker = 0
    real = []
    for v in vals:
        if v is None:
            nulls += 1
            continue
        s = str(v).strip()
        if s == "":
            blank += 1
        elif s.lower() in MISSING_MARKERS:
            marker += 1
        else:
            real.append(s)

    info = {
        "rows": len(vals), "null": nulls, "blank": blank,
        "missing_marker": marker, "distinct": len(set(real)),
    }
    warnings = []
    if blank or marker:
        warnings.append(f"{blank} blank and {marker} missing-marker values (kept separate from NULL)")

    if not real:
        info["type"] = "empty"
    elif all(_is_num(s) for s in real):
        nums = [float(s) for s in real]
        info.update(type="numeric", num_min=min(nums), num_max=max(nums),
                    zero=sum(1 for n in nums if n == 0))
    else:
        parsed = [_parse_date(s) for s in real]
        ok = [p for p in parsed if p]
        if len(ok) / len(real) >= 0.8:
            norms = [p[0] for p in ok]
            info.update(type="date", date_min=min(norms), date_max=max(norms),
                        unparseable=len(real) - len(ok),
                        ambiguous=sum(1 for p in ok if p[1]),
                        mixed_precision=len({len(n) for n in norms}) > 1)
            if info["unparseable"]:
                warnings.append(f"{info['unparseable']} unparseable date values")
            if info["ambiguous"]:
                warnings.append(f"{info['ambiguous']} ambiguous dates (dd/mm vs mm/dd)")
            if info["mixed_precision"]:
                warnings.append("mixed date precision (full date and year-only)")
        else:
            info["type"] = "text"
            if len({s.lower() for s in real}) < len(set(real)):
                warnings.append("case variants of same value (e.g. ACTIVE vs active)")

    if info["rows"] > 1 and info["distinct"] == 1 and not (nulls or blank or marker):
        warnings.append("constant column")
    info["warnings"] = warnings
    return info


def profile_columns(conn, tables: list[str]) -> dict:
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    out = {}
    for t in tables:
        if t not in existing:
            continue  # unknown table -> no info (fail closed)
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({_q(t)})")]
        prof = {c: _profile_column(conn, t, c) for c in cols}
        cols_sql = ", ".join(_q(c) for c in cols)
        dup = conn.execute(
            f"SELECT COALESCE(SUM(c - 1), 0) FROM "
            f"(SELECT COUNT(*) c FROM {_q(t)} GROUP BY {cols_sql} HAVING COUNT(*) > 1)"
        ).fetchone()[0] if cols else 0
        meta_w = [f"{dup} duplicate-like rows"] if dup else []
        prof["__table__"] = {"row_count": conn.execute(f"SELECT COUNT(*) FROM {_q(t)}").fetchone()[0],
                             "duplicate_rows": dup, "warnings": meta_w}
        out[t] = prof
    return out