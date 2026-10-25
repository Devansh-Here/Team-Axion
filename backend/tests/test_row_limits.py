import sqlite3

import pytest

from app.executor import execute_read_only
from app.policy import row_filters
from app.row_limits import apply_row_filters


@pytest.fixture
def db(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite")
    c.executescript("""
        CREATE TABLE sales(order_id TEXT, region TEXT, net_amt REAL, product_id TEXT);
        CREATE TABLE products(product_id TEXT, product_name TEXT);
        INSERT INTO sales VALUES ('1','Delhi',100,'P1'),('2','delhi',50,'P1'),
                                 ('3','Mumbai',1000,'P2'),('4','New Delhi',7,'P1');
        INSERT INTO products VALUES ('P1','Pen'),('P2','Book');
    """)
    yield c
    c.close()


def _total(db, sql, role):
    out = apply_row_filters(sql, row_filters(role, "demo"))
    return db.execute(out).fetchone()[0]


def test_viewer_sees_only_delhi(db):
    assert _total(db, "SELECT SUM(net_amt) FROM sales", "viewer") == 150
    assert _total(db, "SELECT SUM(net_amt) FROM sales", "manager") == 1157


def test_alias_join_subquery_cte(db):
    assert _total(db, "SELECT SUM(s.net_amt) FROM sales s JOIN products p ON p.product_id = s.product_id", "viewer") == 150
    assert _total(db, "SELECT SUM(net_amt) FROM (SELECT * FROM sales)", "viewer") == 150
    assert _total(db, "WITH x AS (SELECT * FROM sales) SELECT SUM(net_amt) FROM x", "viewer") == 150
    assert _total(db, "SELECT (SELECT SUM(net_amt) FROM sales)", "viewer") == 150
    assert _total(db, "SELECT SUM(sales.net_amt) FROM sales", "viewer") == 150


def test_no_filter_table_untouched(db):
    assert _total(db, "SELECT COUNT(*) FROM products", "viewer") == 2


def test_viewer_end_to_end_via_executor(tmp_path):
    """Rewritten SQL read-only executor + authorizer se bhi guzarna chahiye."""
    p = tmp_path / "e.sqlite"
    c = sqlite3.connect(p)
    c.executescript("""
        CREATE TABLE sales(order_id TEXT, region TEXT, net_amt REAL);
        INSERT INTO sales VALUES ('1','Delhi',100),('2','Mumbai',1000);
    """)
    c.close()
    for role, expect in (("viewer", 100), ("manager", 1100)):
        sql = apply_row_filters("SELECT SUM(net_amt) AS t FROM sales", row_filters(role, "demo"))
        out = execute_read_only(str(p), sql, [], timeout_s=5, max_rows=500, max_bytes=2_000_000)
        print("OUT:", out)
        assert out.status == "OK" and out.rows[0][0] == expect

def test_viewer_blocked_when_filtered_table_renamed(tmp_path, monkeypatch):
    import sqlite3
    from app import wiring

    db = tmp_path / "renamed.sqlite"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE sales_v2(order_id TEXT, region TEXT, net_amt TEXT);
        INSERT INTO sales_v2 VALUES ('O-1','Delhi','100'), ('O-2','Mumbai','900');
    """)
    c.commit()
    c.close()

    monkeypatch.setattr(wiring, "_db_path", lambda ds: str(db))
    monkeypatch.setattr(wiring.metadata_db, "init_db", lambda: None)

    deps = wiring.default_deps("viewer")
    out = deps.execute("demo", "SELECT region, SUM(net_amt) FROM sales_v2 GROUP BY region", [])
    print("OUT:", out)
    assert out.status != "OK"
    assert out.error_code == "ROW_FILTER_FAILED"
    assert not any("Mumbai" in str(r) for r in out.rows)