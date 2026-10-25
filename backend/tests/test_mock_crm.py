import sqlite3

from app.mock_crm import build
from app.profiler import profile_columns
from app.policy import CATALOG, permitted_schema


def test_mock_crm_schema_matches_policy_catalog(tmp_path):
    path = build(str(tmp_path / "crm.sqlite"))
    connection = sqlite3.connect(path)
    try:
        for table, columns in CATALOG["crm_demo"].items():
            actual = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            assert actual == columns
    finally:
        connection.close()


def test_mock_crm_preserves_messy_amounts_and_stage_variants(tmp_path):
    path = build(str(tmp_path / "crm.sqlite"))
    connection = sqlite3.connect(path)
    try:
        stages = {row[0] for row in connection.execute("SELECT stage FROM deals")}
        amounts = {row[0] for row in connection.execute("SELECT amount FROM deals")}
        profile = profile_columns(connection, ["deals"])["deals"]
    finally:
        connection.close()
    assert {"Closed Won", "closedwon", "CLOSED WON"} <= stages
    assert {"N/A", "", "-", "1,20,000"} <= amounts
    assert profile["amount"]["type"] == "text"
    assert profile["amount"]["missing_marker"] == 2
    assert profile["amount"]["blank"] == 1


def test_mock_crm_has_duplicate_contacts_and_join_inflation_shape(tmp_path):
    path = build(str(tmp_path / "crm.sqlite"))
    connection = sqlite3.connect(path)
    try:
        duplicate_emails = connection.execute(
            "SELECT lower(email), COUNT(*) FROM contacts GROUP BY lower(email) HAVING COUNT(*) > 1"
        ).fetchall()
        deal_count = connection.execute(
            "SELECT COUNT(*) FROM deals WHERE company_id = 'C-001'"
        ).fetchone()[0]
        joined_count = connection.execute(
            "SELECT COUNT(*) FROM deals d JOIN contacts c ON c.company_id = d.company_id "
            "WHERE d.company_id = 'C-001'"
        ).fetchone()[0]
        mismatches = connection.execute(
            "SELECT COUNT(*) FROM deals WHERE "
            "(lower(stage) LIKE '%won%' AND status != 'WON') OR "
            "(lower(stage) LIKE '%lost%' AND status != 'LOST')"
        ).fetchone()[0]
    finally:
        connection.close()
    assert {row[0] for row in duplicate_emails} == {"asha@acme.example", "ravi@bluebird.example"}
    assert joined_count > deal_count
    assert mismatches >= 1


def test_mock_crm_is_available_to_analyst_but_has_no_write_surface():
    schema = permitted_schema("analyst", "crm_demo")
    assert set(schema) == {"companies", "contacts", "deals", "activities"}
    assert "deals.amount" in {f"{table}.{column}" for table, columns in schema.items() for column in columns}
