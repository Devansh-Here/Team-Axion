"""Synthetic read-only CRM dataset for local analytics demos.

The records are invented and are stored in SQLite only so the existing
policy, profiling, SQL guard, evidence, and audit pipeline can treat the CRM
like any other permitted analytical dataset. No write API is exposed.
"""

import os
import sqlite3


COMPANIES = [
    ("C-001", "Acme Retail", "Retail", "Delhi"),
    ("C-002", "Bluebird Health", "Healthcare", "Mumbai"),
    ("C-003", "Cedar Finance", "Financial Services", "Bengaluru"),
    ("C-004", "Delta Logistics", "Logistics", "Delhi"),
    ("C-005", "Echo Learning", "Education", "Pune"),
]

CONTACTS = [
    # Duplicate business identities are intentional: contact_id is different,
    # while email identifies the same person with case variation.
    ("CT-001", "Asha Mehta", "asha@acme.example", "C-001", "Delhi", "Customer"),
    ("CT-002", "Ravi Shah", "ravi@bluebird.example", "C-002", "Mumbai", "Opportunity"),
    ("CT-003", "Meera Iyer", "meera@cedar.example", "C-003", "Bengaluru", "Customer"),
    ("CT-004", "Kabir Singh", "kabir@delta.example", "C-004", "Delhi", "Lead"),
    ("CT-005", "Nisha Rao", "nisha@echo.example", "C-005", "Pune", "Lead"),
    ("CT-006", "Dev Malhotra", "dev@bluebird.example", "C-002", "Mumbai", "Opportunity"),
    ("CT-007", "Isha Kapoor", "isha@acme.example", "C-001", "Delhi", "Customer"),
    ("CT-008", "ASHA MEHTA", "ASHA@ACME.EXAMPLE", "C-001", "Delhi", "Customer"),
    ("CT-009", "RAVI SHAH", "RAVI@BLUEBIRD.EXAMPLE", "C-002", "Mumbai", "Opportunity"),
]

DEALS = [
    # amount is TEXT on purpose: missing markers, Indian comma formatting,
    # and numeric strings must be profiled instead of silently coerced.
    # deal_id, company_id, owner, stage, amount, probability, created_date, close_date, status
    ("D-090", "C-001", "Asha", "Closed Won", "10000", "1.0", "2025-01-12", "2025-02-20", "WON"),
    ("D-091", "C-002", "Ravi", "Proposal", "16000", "0.6", "15/03/2025", "2025-06-01", "OPEN"),
    ("D-092", "C-003", "Meera", "Closed Lost", "8000", "0.0", "Apr 08, 2025", "2025-05-10", "LOST"),
    ("D-093", "C-004", "Asha", "Qualified", "14000", "0.4", "2025-07-02", "", "OPEN"),
    ("D-100", "C-001", "Asha", "Closed Won", "12000", "1.0", "2026-01-04", "2026-02-15", "WON"),
    ("D-101", "C-002", "Ravi", "Proposal", "18000", "0.6", "12/02/2026", "30/05/2026", "OPEN"),
    ("D-102", "C-003", "Meera", "Negotiation", "25000", "0.7", "05/03/2026", "Mar 05, 2026", "OPEN"),
    ("D-103", "C-004", "Asha", "Closed Lost", "9000", "0.0", "2026-03-20", "2026-04-18", "WON"),
    ("D-104", "C-001", "Asha", "Qualified", "N/A", "0.4", "02/04/2026", "", "OPEN"),
    ("D-105", "C-002", "Ravi", "closedwon", "22000", "1.0", "2026-04-14", "05/22/2026", "WON"),
    ("D-106", "C-003", "Meera", "Proposal", "-", "0.5", "2026-05-11", "Mar 09, 2026", "OPEN"),
    ("D-107", "C-005", "Ravi", "Prospecting", "1,20,000", "0.2", "07/06/2026", "2026-09-12", "OPEN"),
    ("D-108", "C-001", "Asha", "CLOSED WON", "15000", "1.0", "2026-06-18", "2026-07-15", "OPEN"),
    ("D-109", "C-002", "Ravi", "Closed Won", "", "1.0", "Mar 10, 2026", "18/08/2026", "WON"),
    ("D-110", "C-003", "Meera", "Negotiation", "31000", "0.7", "2026-07-02", "2026-09-20", "OPEN"),
    ("D-111", "C-004", "Asha", "Closed Lost", "7000", "0.0", "2026-08-09", "2026-09-30", "LOST"),
]

ACTIVITIES = [
    ("A-090", "CT-001", "Call", "2025-01-20", "Connected"),
    ("A-091", "CT-002", "Email", "2025-03-18", "Replied"),
    ("A-092", "CT-003", "Meeting", "Apr 15, 2025", "Qualified"),
    ("A-001", "CT-001", "Call", "2026-01-10", "Connected"),
    ("A-002", "CT-002", "Email", "10/02/2026", "Replied"),
    ("A-003", "CT-003", "Meeting", "Mar 12, 2026", "Qualified"),
    ("A-004", "CT-004", "Call", "2026-03-25", "No answer"),
    ("A-005", "CT-005", "Email", "2026-04-05", "Opened"),
    ("A-006", "CT-006", "Meeting", "22/04/2026", "Proposal requested"),
    ("A-007", "CT-001", "Meeting", "2026-05-04", "Renewal discussion"),
    ("A-008", "CT-002", "Call", "2026-05-17", "Connected"),
    ("A-009", "CT-003", "Email", "2026-06-01", "Replied"),
    ("A-010", "CT-005", "Call", "2026-06-08", "No answer"),
    ("A-011", "CT-006", "Email", "2026-06-15", "Opened"),
    ("A-012", "CT-007", "Meeting", "2026-06-21", "Connected"),
    ("A-013", "CT-008", "Email", "2026-06-22", "Opened"),
    ("A-014", "CT-009", "Call", "2026-06-23", "Connected"),
]


def build(path: str) -> str:
    """Create the synthetic CRM database at *path* and return that path."""
    if os.path.exists(path):
        os.remove(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE companies(
                company_id TEXT PRIMARY KEY,
                company_name TEXT,
                industry TEXT,
                region TEXT
            );
            CREATE TABLE contacts(
                contact_id TEXT PRIMARY KEY,
                contact_name TEXT,
                email TEXT,
                company_id TEXT,
                region TEXT,
                lifecycle_stage TEXT
            );
            CREATE TABLE deals(
                deal_id TEXT PRIMARY KEY,
                company_id TEXT,
                owner TEXT,
                stage TEXT,
                amount TEXT,
                probability TEXT,
                created_date TEXT,
                close_date TEXT,
                status TEXT
            );
            CREATE TABLE activities(
                activity_id TEXT PRIMARY KEY,
                contact_id TEXT,
                activity_type TEXT,
                activity_date TEXT,
                outcome TEXT
            );
            """
        )
        connection.executemany("INSERT INTO companies VALUES (?,?,?,?)", COMPANIES)
        connection.executemany("INSERT INTO contacts VALUES (?,?,?,?,?,?)", CONTACTS)
        connection.executemany("INSERT INTO deals VALUES (?,?,?,?,?,?,?,?,?)", DEALS)
        connection.executemany("INSERT INTO activities VALUES (?,?,?,?,?)", ACTIVITIES)
        connection.commit()
    finally:
        connection.close()
    return path


if __name__ == "__main__":
    import sys

    output = sys.argv[1] if len(sys.argv) > 1 else "../data/demo/crm_demo.sqlite"
    print(build(output))
