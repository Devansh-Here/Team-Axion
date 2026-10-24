import math

from app.contracts import QueryOutcome
from app.result_checks import validate_result


def codes(report):
    return {check["code"]: check["status"] for check in report.checks}


def test_empty_result_is_explicit_warning_not_fabricated_answer():
    report = validate_result(
        "Which categories are active?",
        "SELECT category FROM products",
        QueryOutcome(status="OK", columns=["category"], rows=[], row_count=0),
        {},
    )

    assert report.acceptable is True
    assert codes(report)["EMPTY_RESULT"] == "WARNING"
    assert "NO_ROWS_MATCHED" in report.warnings


def test_all_null_result_is_blocked():
    report = validate_result(
        "What is the total?",
        "SELECT SUM(net_amt) AS total FROM sales",
        QueryOutcome(status="OK", columns=["total"], rows=[[None]], row_count=1),
        {},
    )

    assert report.acceptable is False
    assert codes(report)["ALL_NULL_RESULT"] == "BLOCKED"


def test_non_finite_number_is_blocked():
    report = validate_result(
        "What is the value?",
        "SELECT value FROM metrics",
        QueryOutcome(status="OK", columns=["value"], rows=[[math.inf]], row_count=1),
        {},
    )

    assert report.acceptable is False
    assert codes(report)["NON_FINITE_NUMBERS"] == "BLOCKED"


def test_truncated_aggregate_is_blocked():
    report = validate_result(
        "Total sales by region",
        "SELECT region, SUM(net_amt) FROM sales GROUP BY region",
        QueryOutcome(status="OK", columns=["region", "total"], rows=[["N", 5]], row_count=1, truncated=True),
        {},
    )

    assert report.acceptable is False
    assert codes(report)["TRUNCATED_RESULT"] == "BLOCKED"


def test_ambiguous_dates_need_clarification():
    profile = {
        "sales": {
            "columns": {
                "order_date": {"warnings": ["AMBIGUOUS_DATES"]},
            }
        }
    }
    report = validate_result(
        "Which categories declined last year?",
        "SELECT category FROM sales",
        QueryOutcome(status="OK", columns=["category"], rows=[["A"]], row_count=1),
        profile,
    )

    assert report.acceptable is False
    assert report.needs_clarification is True
    assert codes(report)["TEMPORAL_COMPARABILITY"] == "WARNING"


def test_join_duplicate_risk_is_visible_warning():
    profile = {"sales": {"duplicate_like_rows": 2, "columns": {}}}
    report = validate_result(
        "Show sales by customer",
        "SELECT c.customer_name, SUM(s.net_amt) FROM sales s JOIN customers c ON c.customer_id = s.customer_id GROUP BY c.customer_name",
        QueryOutcome(status="OK", columns=["customer_name", "total"], rows=[["A", 10]], row_count=1),
        profile,
    )

    assert report.acceptable is True
    assert codes(report)["JOIN_INFLATION"] == "WARNING"


def test_failed_execution_is_blocked():
    report = validate_result(
        "What is the total?",
        "SELECT SUM(net_amt) FROM sales",
        QueryOutcome(status="TIMEOUT", error_code="QUERY_TIMEOUT"),
        {},
    )

    assert report.acceptable is False
    assert codes(report)["EXECUTION_STATUS"] == "BLOCKED"
