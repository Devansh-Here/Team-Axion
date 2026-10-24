"""Synthetic demo DB (Lane B). Invented data only. Run: python -m app.demo_data"""
import hashlib
import os
import sqlite3
import sys

SALES = [
    # order_id, order_date, product_id, region, net_amt, status
    ("S-001", "2024-02-10", "P-1", "Delhi",     "1000",    "ACTIVE"),
    ("S-002", "2024-05-15", "P-2", "Delhi",     "500",     "ACTIVE"),
    ("S-003", "2024-07-01", "P-3", "delhi",     "800",     "active"),
    ("S-004", "2024-09-20", "P-4", "Mumbai",    "200",     "ACTIVE"),
    ("S-005", "2024-11-11", "P-1", "New Delhi", "1700",    "CLOSED"),
    ("S-006", "2025-01-04", "P-1", "Delhi",     "1200.50", "ACTIVE"),
    ("S-007", "04/01/2025", "P-2", "delhi",     "N/A",     "active"),   # ambiguous date + missing amt
    ("S-008", "2025",       "P-1", "New Delhi", "-",       "ACTIVE"),   # year-only date + missing amt
    ("S-009", "2025-02-14", "P-3", "Delhi",     "0",       "CLOSED"),   # real zero, not missing
    ("S-010", "2025-03-03", "P-4", "Mumbai",    "450",     "ACTIVE"),
    ("S-011", "2025-06-18", "P-3", "Mumbai",    "350",     "ACTIVE"),
    ("S-009", "2025-02-14", "P-3", "Delhi",     "0",       "CLOSED"),   # duplicate-like row
]
PRODUCTS = [("P-1", "Laptop", "Electronics"), ("P-2", "Phone", "Electronics"),
            ("P-3", "Desk", "Furniture"), ("P-4", "Notebook", "Stationery")]
CUSTOMERS = [("C-1", "Asha", "Delhi"), ("C-2", "Ravi", "Mumbai"), ("C-3", "Meera", "New Delhi")]
EMPLOYEES = [("E-1", "Sales", "50000"), ("E-2", "Sales", "60000"), ("E-3", "Ops", "45000")]


def build(path: str) -> str:
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE sales(order_id TEXT, order_date TEXT, product_id TEXT, region TEXT, net_amt TEXT, status TEXT)")
    c.execute("CREATE TABLE products(product_id TEXT PRIMARY KEY, product_name TEXT, category TEXT)")
    c.execute("CREATE TABLE customers(customer_id TEXT PRIMARY KEY, customer_name TEXT, region TEXT)")
    c.execute("CREATE TABLE employees(employee_id TEXT PRIMARY KEY, department TEXT, salary TEXT)")
    c.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?)", SALES)
    c.executemany("INSERT INTO products VALUES (?,?,?)", PRODUCTS)
    c.executemany("INSERT INTO customers VALUES (?,?,?)", CUSTOMERS)
    c.executemany("INSERT INTO employees VALUES (?,?,?)", EMPLOYEES)
    c.commit()
    c.close()
    return path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "../data/demo/demo.sqlite"
    build(out)
    print(out, hashlib.sha256(open(out, "rb").read()).hexdigest())