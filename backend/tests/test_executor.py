import hashlib
import sqlite3

import pytest
from app.executor import execute_read_only


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "t.sqlite"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE sales (order_id INTEGER, region TEXT, net_amt REAL)")
    c.executemany("INSERT INTO sales VALUES (?,?,?)",
                  [(i, "north" if i % 2 else "south", i * 1.5) for i in range(2000)])
    c.commit()
    c.close()
    return str(p)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def run(db, sql, params=None, timeout_s=2.0, max_rows=500, max_bytes=2_000_000):
    return execute_read_only(db, sql, params or [], timeout_s=timeout_s,
                             max_rows=max_rows, max_bytes=max_bytes)


def test_normal_select(db):
    r = run(db, "SELECT region, SUM(net_amt) FROM sales GROUP BY region ORDER BY region")
    assert r.status == "OK" and r.row_count == 2 and not r.truncated


def test_params_are_bound(db):
    r = run(db, "SELECT COUNT(*) FROM sales WHERE region = ?", ["north"])
    assert r.status == "OK" and r.rows[0][0] == 1000


def test_injection_in_param_is_just_a_string(db):
    r = run(db, "SELECT COUNT(*) FROM sales WHERE region = ?", ["x'; DROP TABLE sales; --"])
    assert r.status == "OK" and r.rows[0][0] == 0
    assert run(db, "SELECT COUNT(*) FROM sales").rows[0][0] == 2000


@pytest.mark.parametrize("sql", [
    "DROP TABLE sales",
    "UPDATE sales SET net_amt = 0",
    "DELETE FROM sales",
    "INSERT INTO sales VALUES (1,'x',1)",
    "CREATE TABLE x (a INT)",
    "ALTER TABLE sales ADD COLUMN z INT",
    "ATTACH DATABASE ':memory:' AS m",
    "PRAGMA writable_schema = 1",
    "PRAGMA journal_mode = DELETE",
    "SELECT name FROM sqlite_master",
    "SELECT load_extension('x')",
    "SELECT randomblob(10)",
    "SELECT 1; DROP TABLE sales",
])
def test_attacks_blocked_and_db_unchanged(db, sql):
    before = sha(db)
    r = run(db, sql)
    assert r.status in ("REJECTED", "ERROR")
    assert sha(db) == before
    assert run(db, "SELECT COUNT(*) FROM sales").rows[0][0] == 2000


def test_row_cap_sets_truncated(db):
    r = run(db, "SELECT order_id FROM sales", max_rows=100)
    assert r.status == "OK" and r.row_count == 100 and r.truncated


def test_byte_cap_sets_truncated(db):
    r = run(db, "SELECT order_id, region FROM sales", max_bytes=500)
    assert r.truncated and r.row_count < 2000


def test_million_row_result_is_capped(db):
    sql = ("WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x < 1000000) "
           "SELECT x FROM n")
    r = run(db, sql, max_rows=500)
    assert r.status == "OK" and r.row_count == 500 and r.truncated


def test_huge_cross_join_times_out(db):
    sql = "SELECT COUNT(*) FROM sales a, sales b, sales c, sales d"
    r = run(db, sql, timeout_s=0.5)
    assert r.status == "TIMEOUT"
    assert r.elapsed_ms < 3000


def test_missing_db_is_safe_error(tmp_path):
    r = run(str(tmp_path / "nope.sqlite"), "SELECT 1")
    assert r.status == "ERROR" and r.error_code == "DB_NOT_FOUND"


def test_error_does_not_leak_raw_message(db):
    r = run(db, "SELECT secret_col FROM sales")
    assert r.status == "ERROR" and r.error_code == "SQL_ERROR"