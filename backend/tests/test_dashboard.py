import sqlite3

from app.dashboard import build_crm_dashboard
from app.mock_crm import build


def test_crm_dashboard_contains_year_comparison_charts_and_quality_flags(tmp_path):
    connection = sqlite3.connect(build(str(tmp_path / "crm.sqlite")))
    try:
        dashboard = build_crm_dashboard(connection)
    finally:
        connection.close()

    assert dashboard["current_year"] == 2026
    assert dashboard["previous_year"] == 2025
    assert dashboard["periods"]["comparable"] is True
    assert {chart["id"] for chart in dashboard["charts"]} >= {
        "deal_volume_by_year",
        "won_deals_by_year",
        "deals_by_stage",
        "contacts_by_lifecycle",
        "activities_by_type",
    }
    assert dashboard["data_quality"]["duplicate_email_groups"] == 2
    assert dashboard["data_quality"]["missing_amounts"] == 3
    assert dashboard["data_quality"]["stage_status_mismatches"] >= 1
    assert any(item["severity"] == "warning" for item in dashboard["insights"])
