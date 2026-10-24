import sqlite3
import pytest


@pytest.fixture
def demo_db(tmp_path):
    path = tmp_path / "demo.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE products(product_id TEXT PRIMARY KEY, product_name TEXT, category TEXT);
    CREATE TABLE sales(order_id TEXT, order_date TEXT, product_id TEXT,
                       region TEXT, net_amt TEXT, status TEXT);
    INSERT INTO products VALUES ('P-1','Laptop','Electronics'),
                                ('P-2','Mouse','Electronics'),
                                ('P-3','Desk','Furniture');
    INSERT INTO sales VALUES
      ('O-001','2025-01-04','P-1','Delhi','1200.50','ACTIVE'),
      ('O-002','04/01/2025','P-2','delhi','N/A','active'),
      ('O-003','2025','P-1','New Delhi','-',''),
      ('O-004','2025-02-14','P-3','Delhi','0','CLOSED');
    """)
    conn.commit()
    conn.close()
    return str(path)