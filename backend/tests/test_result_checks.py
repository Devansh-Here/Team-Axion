import sqlite3
from app.contracts import QueryOutcome
from app.demo_data import build
from app.mock_crm import build as build_crm
from app.profiler import profile_columns
from app.result_checks import validate_result

SQL = "SELECT SUM(net_amt) FROM sales WHERE order_date >= '2025-01-01'"
PROFILE = {"sales": {
    "net_amt": {"blank": 0, "missing_marker": 2},
    "order_date": {"ambiguous": 1, "unparseable": 0, "mixed_precision": True},
    "__table__": {"row_count": 12}}}


def out(rows, **kw):
    return QueryOutcome(status="OK", columns=["x"], rows=rows, row_count=len(rows), **kw)


def codes(rep):
    return {c["code"] for c in rep.checks}


def test_empty_result_warns_not_blocks():  # T-012
    rep = validate_result("q", SQL, out([]), {})
    assert rep.acceptable and "EMPTY_RESULT" in codes(rep)
    assert "No rows matched" in rep.warnings[0]


def test_all_null_blocked_no_zero_invented():  # T-013
    rep = validate_result("q", SQL, out([[None]]), {})
    assert not rep.acceptable and "ALL_NULL" in codes(rep)


def test_truncated_warns():  # T-017
    rep = validate_result("q", SQL, out([[1.0]], truncated=True), {})
    assert rep.acceptable and "TRUNCATED" in codes(rep)


def test_non_finite_blocked():
    rep = validate_result("q", SQL, out([[float("inf")]]), {})
    assert not rep.acceptable and "NON_FINITE" in codes(rep)


def test_non_ok_outcome_blocked():
    bad = QueryOutcome(status="ERROR", error_code="x")
    assert not validate_result("q", SQL, bad, {}).acceptable


def test_missing_markers_and_dates_warn():
    c = codes(validate_result("q", SQL, out([[1200.5]]), PROFILE))
    assert {"MISSING_MARKERS", "AMBIGUOUS_DATES", "MIXED_DATE_PRECISION"} <= c


def test_unrelated_table_not_warned():
    rep = validate_result("q", "SELECT category FROM products", out([["A"]]), PROFILE)
    assert rep.acceptable and not rep.warnings


def test_crm_deal_contact_aggregation_warns_about_join_inflation():
    sql = (
        "SELECT d.owner, SUM(CAST(d.amount AS REAL)) FROM deals d "
        "JOIN contacts c ON c.company_id = d.company_id GROUP BY d.owner"
    )
    rep = validate_result("won revenue by owner", sql, out([[1.0]]), {})
    assert rep.acceptable and "JOIN_INFLATION_RISK" in codes(rep)


def test_dirty_crm_amount_aggregation_is_blocked(tmp_path):
    conn = sqlite3.connect(build_crm(str(tmp_path / "crm.sqlite")))
    profile = profile_columns(conn, ["deals"])
    rep = validate_result("total pipeline", "SELECT SUM(amount) FROM deals", out([[1.0]]), profile)
    assert not rep.acceptable
    assert "DIRTY_NUMERIC_AGGREGATION" in codes(rep)


def test_dirty_crm_amount_ranking_is_blocked(tmp_path):
    conn = sqlite3.connect(build_crm(str(tmp_path / "crm.sqlite")))
    profile = profile_columns(conn, ["deals"])
    sql = "SELECT deal_id FROM deals ORDER BY amount DESC LIMIT 1"
    rep = validate_result("largest opportunity", sql, out([["D-107"]]), profile)
    assert not rep.acceptable
    assert "DIRTY_NUMERIC_AGGREGATION" in codes(rep)


def test_real_demo_db_end_to_end(tmp_path):
    conn = sqlite3.connect(build(str(tmp_path / "d.sqlite")))
    prof = profile_columns(conn, ["sales"])
    rep = validate_result("q", SQL, out([[1200.5]]), prof)
    assert rep.acceptable and "MISSING_MARKERS" in codes(rep)
