import pytest
from app.policy import authorize, permitted_schema

Q_OK = "Total net sales by category in 2025"
Q_SALARY = "Average employee salary by department"


def test_analyst_normal_question_allowed():
    d = authorize("analyst", "demo", Q_OK)
    assert d.action == "ALLOW"
    assert "sales" in d.allowed_tables and "employees" in d.allowed_tables
    assert "sales.net_amt" in d.allowed_columns


def test_salary_column_never_allowed():
    d = authorize("analyst", "demo", Q_OK)
    assert "employees.salary" not in d.allowed_columns


def test_permitted_schema_strips_salary():
    s = permitted_schema("analyst", "demo")
    assert "salary" not in s["employees"]
    assert "department" in s["employees"]


def test_viewer_has_no_employees_table():
    s = permitted_schema("viewer", "demo")
    assert "employees" not in s


def test_salary_question_analyst_is_ask_with_no_access():
    d = authorize("analyst", "demo", Q_SALARY)
    assert d.action == "ASK"
    assert d.allowed_tables == set() and d.allowed_columns == set()


def test_salary_question_viewer_is_deny():
    d = authorize("viewer", "demo", Q_SALARY)
    assert d.action == "DENY"
    assert d.allowed_tables == set()


@pytest.mark.parametrize("q", [
    "what is the PAYROLL total", "show wages by dept", "employee compensation",
    "SALARIES of staff",
])
def test_protected_terms_caught(q):
    assert authorize("analyst", "demo", q).action == "ASK"


@pytest.mark.parametrize("role", ["", "admin", "root", None, "ANALYST"])
def test_unknown_role_denied(role):
    assert authorize(role, "demo", Q_OK).action == "DENY"


def test_unknown_dataset_denied():
    assert authorize("analyst", "nope", Q_OK).action == "DENY"


def test_non_string_question_does_not_crash():
    assert authorize("analyst", "demo", None).action == "ALLOW"


def test_reason_codes_do_not_leak_column_names():
    for role, q in [("analyst", Q_SALARY), ("viewer", Q_SALARY), ("bad", Q_OK)]:
        d = authorize(role, "demo", q)
        assert "salary" not in d.reason_code.lower()