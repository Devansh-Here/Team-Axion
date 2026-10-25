import sqlite3

import pytest

from app.executor import execute_read_only
from app.policy import authorize, permitted_schema
from app.sql_guard import validate_candidate
from tests.test_dynamic_catalog import env, _register  # noqa: F401

DS = "up1"
EXPECT = [("North", 1), ("South", 1)]


def _check(res, sql):
    """Guard + executor current catalog pe. True = allowed aur sahi rows aayi."""
    pol = authorize("analyst", DS, "total orders by region")
    verdict = validate_candidate(sql, pol.allowed_tables, pol.allowed_columns)
    if type(verdict).__name__ != "Allow":
        return False
    out = execute_read_only(res.db_path, sql, [], timeout_s=5,
                            max_rows=500, max_bytes=2_000_000)
    return out.status == "OK" and sorted(map(tuple, out.rows)) == sorted(EXPECT)


def _alter(res, *stmts):
    c = sqlite3.connect(res.db_path)
    for s in stmts:
        c.execute(s)
    c.commit()
    c.close()


def test_before(env):
    res = _register(env)
    assert permitted_schema("analyst", DS) == {"orders": ["order_id", "region", "net_amt"]}
    assert _check(res, "SELECT region, COUNT(order_id) FROM orders GROUP BY region")


def test_after_table_rename(env):
    res = _register(env)
    permitted_schema("analyst", DS)                       # cache warm
    _alter(res, "ALTER TABLE orders RENAME TO sales_orders")
    s = permitted_schema("analyst", DS)
    assert "sales_orders" in s and "orders" not in s
    assert not _check(res, "SELECT region, COUNT(order_id) FROM orders GROUP BY region")
    assert _check(res, "SELECT region, COUNT(order_id) FROM sales_orders GROUP BY region")


def test_after_column_rename(env):
    res = _register(env)
    permitted_schema("analyst", DS)
    _alter(res, "ALTER TABLE orders RENAME COLUMN net_amt TO net_amount")
    cols = permitted_schema("analyst", DS)["orders"]
    assert "net_amount" in cols and "net_amt" not in cols
    assert _check(res, "SELECT region, COUNT(order_id) FROM orders "
                       "GROUP BY region HAVING COUNT(net_amount) >= 0")


def test_after_table_split(env):
    res = _register(env)
    permitted_schema("analyst", DS)
    _alter(res,
           "CREATE TABLE order_facts AS SELECT order_id, net_amt FROM orders",
           "CREATE TABLE order_geo AS SELECT order_id, region FROM orders",
           "DROP TABLE orders")
    assert set(permitted_schema("analyst", DS)) == {"order_facts", "order_geo"}
    assert _check(res, "SELECT g.region, COUNT(f.order_id) FROM order_geo g "
                       "JOIN order_facts f ON f.order_id = g.order_id GROUP BY g.region")


def test_renamed_sensitive_column_stays_hidden(env):
    res = _register(env)
    permitted_schema("analyst", DS)                      # snapshot yahin banta hai
    _alter(res, "ALTER TABLE orders RENAME COLUMN monthly_salary TO m_sal")
    cols = permitted_schema("analyst", DS)["orders"]
    assert "m_sal" not in cols and "monthly_salary" not in cols
    assert "net_amt" in cols and "region" in cols        # baaki normal columns dikhte rahe


def test_corrupt_snapshot_fails_closed(env):
    res = _register(env)
    permitted_schema("analyst", DS)
    from pathlib import Path
    Path(res.db_path + ".protected.json").write_text("{not json", encoding="utf-8")
    from app.policy import _SNAP_CACHE
    _SNAP_CACHE.clear()
    assert permitted_schema("analyst", DS) == {}         # sab hidden = koi table nahi