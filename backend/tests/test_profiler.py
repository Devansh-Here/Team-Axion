import sqlite3
import pytest
from app.profiler import profile_columns


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE sales(order_id TEXT, order_date TEXT, region TEXT, net_amt TEXT, status TEXT)")
    c.executemany("INSERT INTO sales VALUES (?,?,?,?,?)", [
        ("O-001", "2025-01-04", "Delhi", "1200.50", "ACTIVE"),
        ("O-002", "04/01/2025", "delhi", "N/A", "active"),
        ("O-003", "2025", "New Delhi", "-", ""),
        ("O-004", "2025-02-14", "Delhi", "0", "CLOSED"),
        ("O-005", "2025-02-14", None, None, "CLOSED"),
        ("O-004", "2025-02-14", "Delhi", "0", "CLOSED"),  # duplicate of O-004
    ])
    return c


def test_null_blank_marker_zero_distinct(conn):  # T-009
    p = profile_columns(conn, ["sales"])["sales"]
    amt = p["net_amt"]
    assert amt["null"] == 1
    assert amt["missing_marker"] == 2          # N/A and -
    assert amt["zero"] == 2                    # zero is NOT missing
    assert p["status"]["blank"] == 1


def test_ambiguous_date_flagged(conn):  # T-010
    d = profile_columns(conn, ["sales"])["sales"]["order_date"]
    assert d["type"] == "date"
    assert d["ambiguous"] == 1
    assert d["mixed_precision"] is True
    assert d["date_min"] == "2025" and d["date_max"] == "2025-02-14"


def test_case_variants_warned(conn):
    w = profile_columns(conn, ["sales"])["sales"]["status"]["warnings"]
    assert any("case variants" in x for x in w)


def test_duplicate_like_rows(conn):
    meta = profile_columns(conn, ["sales"])["sales"]["__table__"]
    assert meta["duplicate_rows"] == 1 and meta["row_count"] == 6


def test_unknown_table_skipped(conn):
    assert profile_columns(conn, ["nope"]) == {}


def test_does_not_mutate(conn):
    before = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    profile_columns(conn, ["sales"])
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == before