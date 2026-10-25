import sqlite3
from app.demo_data import build
from app.profiler import profile_columns
from app.policy import CATALOG


def test_schema_matches_policy_catalog(tmp_path):
    conn = sqlite3.connect(build(str(tmp_path / "d.sqlite")))
    for t, cols in CATALOG["demo"].items():
        assert [r[1] for r in conn.execute(f"PRAGMA table_info({t})")] == cols


def test_category_totals_2025(tmp_path):
    conn = sqlite3.connect(build(str(tmp_path / "d.sqlite")))
    rows = dict(conn.execute(
        "SELECT p.category, SUM(CAST(s.net_amt AS REAL)) FROM sales s JOIN products p USING(product_id) "
        "WHERE s.order_date >= '2025-01-01' AND s.order_date < '2026-01-01' GROUP BY p.category"))
    assert rows == {"Electronics": 1200.5, "Furniture": 350.0, "Stationery": 450.0}


def test_profile_flags_mess_and_no_history_before_2024(tmp_path):
    conn = sqlite3.connect(build(str(tmp_path / "d.sqlite")))
    p = profile_columns(conn, ["sales"])["sales"]
    assert p["order_date"]["ambiguous"] == 1 and p["order_date"]["mixed_precision"] is True
    assert p["net_amt"]["missing_marker"] == 2 and p["net_amt"]["zero"] == 2
    assert p["order_date"]["date_min"].startswith("2024")
    assert p["__table__"]["duplicate_rows"] == 1