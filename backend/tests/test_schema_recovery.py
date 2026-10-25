import sqlite3

from app.mock_crm import build
from app.schema_recovery import recover_permitted_schema


def test_recovery_handles_renamed_deals_table(tmp_path):
    original = build(str(tmp_path / "crm.sqlite"))
    changed = tmp_path / "renamed.sqlite"
    source = sqlite3.connect(original)
    target = sqlite3.connect(changed)
    try:
        target.executescript(
            "CREATE TABLE companies(company_id TEXT, company_name TEXT, industry TEXT, region TEXT);"
            "CREATE TABLE contacts(contact_id TEXT, contact_name TEXT, email TEXT, company_id TEXT, region TEXT, lifecycle_stage TEXT);"
            "CREATE TABLE activities(activity_id TEXT, contact_id TEXT, activity_type TEXT, activity_date TEXT, outcome TEXT);"
            "CREATE TABLE opportunities(deal_id TEXT, company_id TEXT, owner TEXT, stage TEXT, amount TEXT, probability TEXT, created_date TEXT, close_date TEXT, status TEXT);"
        )
        for table in ("companies", "contacts", "activities"):
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            target.executemany(f"INSERT INTO {table} VALUES ({','.join('?' for _ in rows[0])})", rows)
        rows = source.execute("SELECT * FROM deals").fetchall()
        target.executemany(f"INSERT INTO opportunities VALUES ({','.join('?' for _ in rows[0])})", rows)
        target.commit()
    finally:
        source.close()
        target.close()
    schema = recover_permitted_schema(str(changed), "analyst", "crm_demo")
    assert "opportunities" in schema
    assert "amount" in schema["opportunities"]


def test_recovery_handles_split_deals_tables(tmp_path):
    original = build(str(tmp_path / "crm.sqlite"))
    changed = tmp_path / "split.sqlite"
    source = sqlite3.connect(original)
    target = sqlite3.connect(changed)
    try:
        target.executescript(
            "CREATE TABLE deal_core(deal_id TEXT, company_id TEXT, owner TEXT, stage TEXT, created_date TEXT, close_date TEXT, status TEXT);"
            "CREATE TABLE deal_financials(deal_id TEXT, amount TEXT, probability TEXT);"
        )
        rows = source.execute(
            "SELECT deal_id, company_id, owner, stage, created_date, close_date, status FROM deals"
        ).fetchall()
        target.executemany("INSERT INTO deal_core VALUES (?,?,?,?,?,?,?)", rows)
        amounts = source.execute("SELECT deal_id, amount, probability FROM deals").fetchall()
        target.executemany("INSERT INTO deal_financials VALUES (?,?,?)", amounts)
        target.commit()
    finally:
        source.close()
        target.close()
    schema = recover_permitted_schema(str(changed), "analyst", "crm_demo")
    assert {"deal_core", "deal_financials"} <= set(schema)
