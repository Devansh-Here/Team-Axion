import pytest
from app.sql_guard import validate_candidate, Allow, Reject

TABLES = {"sales", "products", "customers", "employees"}
COLUMNS = {
    "sales.order_id", "sales.order_date", "sales.product_id",
    "sales.region", "sales.net_amt", "sales.status",
    "products.product_id", "products.product_name", "products.category",
    "customers.customer_id", "customers.customer_name", "customers.region",
    # employees ka salary JAAN BOOJH ke allowed nahi hai
    "employees.employee_id", "employees.department",
}


def check(sql):
    return validate_candidate(sql, TABLES, COLUMNS)


# ---------- ye allow hone chahiye ----------
@pytest.mark.parametrize("sql", [
    "SELECT order_id, net_amt FROM sales",
    "SELECT order_id FROM sales;",
    "SELECT p.category, SUM(s.net_amt) AS total FROM sales s "
    "JOIN products p ON p.product_id = s.product_id GROUP BY p.category ORDER BY total DESC",
    "WITH t AS (SELECT region, net_amt FROM sales) SELECT region, SUM(net_amt) FROM t GROUP BY region",
    "SELECT region FROM sales WHERE net_amt > (SELECT AVG(net_amt) FROM sales)",
    "SELECT COUNT(*) FROM sales",
    "SELECT region FROM sales UNION SELECT region FROM customers",
    "SELECT ROUND(SUM(net_amt), 2) FROM sales WHERE region = ?",
    "SELECT department FROM employees",
    "SELECT strftime('%Y', order_date) AS yr, SUM(net_amt) FROM sales GROUP BY yr",
    "SELECT order_id FROM sales /* ; DROP TABLE sales */",
])
def test_allowed(sql):
    assert isinstance(check(sql), Allow), check(sql)


# ---------- ye reject hone chahiye ----------
@pytest.mark.parametrize("sql", [
    "DROP TABLE sales",
    "UPDATE sales SET net_amt = 0",
    "DELETE FROM sales",
    "INSERT INTO sales (order_id) VALUES (1)",
    "CREATE TABLE x (a INT)",
    "ALTER TABLE sales ADD COLUMN z INT",
    "ATTACH DATABASE 'evil.db' AS evil",
    "PRAGMA table_info(sales)",
    "PRAGMA writable_schema = 1",
    "SELECT order_id FROM sales; DROP TABLE sales",
    "SELECT order_id FROM sales; /* x */ DROP TABLE sales",
    "SELECT order_id FROM sales; -- c\nDROP TABLE sales",
    "",
    "   ",
    "this is not sql at all",
])
def test_rejected_statements(sql):
    assert isinstance(check(sql), Reject)


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sales",
    "SELECT s.* FROM sales s",
    "SELECT salary FROM employees",
    "SELECT e.salary FROM employees e",
    "SELECT salary AS x FROM employees",
    "WITH t AS (SELECT salary FROM employees) SELECT salary FROM t",
    "SELECT department FROM employees WHERE salary > 100",
    "SELECT department FROM employees ORDER BY salary",
    "SELECT name FROM (SELECT salary AS name FROM employees)",
    "SELECT region FROM sales WHERE net_amt > (SELECT MAX(salary) FROM employees)",
    "SELECT fake_col FROM sales",
])
def test_denied_columns_and_star(sql):
    assert isinstance(check(sql), Reject)


@pytest.mark.parametrize("sql", [
    "SELECT name FROM sqlite_master",
    "SELECT order_id FROM main.sales",
    "SELECT name FROM pragma_table_info('sales')",
    "SELECT order_id FROM sales JOIN secret_table ON 1=1",
    "SELECT load_extension('evil.dll')",
    "SELECT readfile('/etc/passwd')",
    "SELECT randomblob(1000000000)",
    "WITH employees AS (SELECT salary FROM employees) SELECT 1",
    "WITH RECURSIVE r AS (SELECT 1 UNION ALL SELECT 1 FROM r) SELECT * FROM r",
])
def test_denied_tables_and_functions(sql):
    assert isinstance(check(sql), Reject)


def test_non_string_input():
    assert isinstance(validate_candidate(None, TABLES, COLUMNS), Reject)


def test_reject_reason_never_leaks_column_names():
    r = check("SELECT salary FROM employees")
    assert isinstance(r, Reject)
    assert "salary" not in r.reason.lower()