"""Deterministic, read-only dashboard metrics for the synthetic CRM demo."""

from collections import Counter
from datetime import datetime
import re
import sqlite3


_MISSING = {"", "n/a", "na", "-", "unknown"}
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%b %d, %Y",
    "%B %d, %Y",
)


def _parse_year(value) -> int | None:
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}", text):
        return int(text)
    for date_format in _DATE_FORMATS:
        try:
            return datetime.strptime(text, date_format).year
        except ValueError:
            continue
    return None


def _rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(f'SELECT * FROM "{table}"')]


def _label(value, fallback: str = "Blank") -> str:
    text = str(value or "").strip()
    return text or fallback


def _chart(chart_id: str, title: str, labels: list[str], values: list[int], detail: str) -> dict:
    return {
        "id": chart_id,
        "title": title,
        "type": "bar",
        "labels": labels,
        "values": values,
        "detail": detail,
    }


def _change(current: int, previous: int) -> dict:
    absolute = current - previous
    percent = None if previous == 0 else round((absolute / previous) * 100, 1)
    return {"current": current, "previous": previous, "absolute": absolute, "percent": percent}


def build_crm_dashboard(connection: sqlite3.Connection) -> dict:
    """Build counts and quality signals without coercing dirty money values."""
    companies = _rows(connection, "companies")
    contacts = _rows(connection, "contacts")
    deals = _rows(connection, "deals")
    activities = _rows(connection, "activities")

    deal_years = {year for row in deals if (year := _parse_year(row.get("created_date")))}
    current_year = max(deal_years) if deal_years else None
    previous_year = current_year - 1 if current_year is not None else None

    current_deals = [row for row in deals if _parse_year(row.get("created_date")) == current_year]
    previous_deals = [row for row in deals if _parse_year(row.get("created_date")) == previous_year]
    current_won = [row for row in current_deals if _label(row.get("status")).upper() == "WON"]
    previous_won = [row for row in previous_deals if _label(row.get("status")).upper() == "WON"]

    stage_counts = Counter(_label(row.get("stage")) for row in deals)
    lifecycle_counts = Counter(_label(row.get("lifecycle_stage")) for row in contacts)
    activity_counts = Counter(_label(row.get("activity_type")) for row in activities)

    email_groups = Counter(_label(row.get("email")).lower() for row in contacts)
    duplicate_email_groups = sum(1 for email, count in email_groups.items() if email not in _MISSING and count > 1)
    missing_amounts = sum(
        1 for row in deals if str(row.get("amount") or "").strip().lower() in _MISSING
    )
    comma_amounts = sum(
        1 for row in deals if re.fullmatch(r"\d{1,3}(?:,\d{2,3})+", str(row.get("amount") or "").strip())
    )
    blank_close_dates = sum(1 for row in deals if not str(row.get("close_date") or "").strip())
    stage_status_mismatches = sum(
        1
        for row in deals
        if ("won" in _label(row.get("stage")).lower() and _label(row.get("status")).upper() != "WON")
        or ("lost" in _label(row.get("stage")).lower() and _label(row.get("status")).upper() != "LOST")
    )

    quality_flags = [
        duplicate_email_groups,
        missing_amounts,
        comma_amounts,
        blank_close_dates,
        stage_status_mismatches,
    ]
    quality_flag_count = sum(value > 0 for value in quality_flags)
    year_label = str(current_year) if current_year is not None else "Unavailable"
    previous_label = str(previous_year) if previous_year is not None else "Unavailable"
    deal_change = _change(len(current_deals), len(previous_deals))
    won_change = _change(len(current_won), len(previous_won))

    insights = []
    if current_year is not None and previous_year is not None:
        direction = "up" if deal_change["absolute"] >= 0 else "down"
        insights.append({
            "severity": "info",
            "title": f"Deal volume is {direction} versus {previous_year}",
            "detail": (
                f"{len(current_deals)} deals in {current_year} versus {len(previous_deals)} in {previous_year}. "
                "This is an observed change, not a causal conclusion."
            ),
        })
    if missing_amounts or comma_amounts:
        insights.append({
            "severity": "warning",
            "title": "Pipeline value is not safe to total yet",
            "detail": (
                f"{missing_amounts} amount values are missing markers and {comma_amounts} use comma formatting. "
                "Value-based totals and rankings are blocked until the field is normalized."
            ),
        })
    if duplicate_email_groups:
        insights.append({
            "severity": "warning",
            "title": "Duplicate contact identities detected",
            "detail": f"{duplicate_email_groups} normalized email group(s) contain multiple contact IDs; raw counts may be inflated.",
        })
    if stage_status_mismatches:
        insights.append({
            "severity": "warning",
            "title": "Stage and status disagree",
            "detail": f"{stage_status_mismatches} deal(s) have a closed-looking stage that does not match status.",
        })

    return {
        "dataset_id": "crm_demo",
        "current_year": current_year,
        "previous_year": previous_year,
        "periods": {"current": year_label, "previous": previous_label, "comparable": bool(previous_deals)},
        "kpis": [
            {"label": f"Deals in {year_label}", "value": len(current_deals), "detail": f"{len(previous_deals)} in {previous_label}"},
            {"label": f"Won deals in {year_label}", "value": len(current_won), "detail": f"{len(previous_won)} in {previous_label}"},
            {"label": "Contacts", "value": len(contacts), "detail": f"{duplicate_email_groups} duplicate email group(s)"},
            {"label": "Data-quality flags", "value": quality_flag_count, "detail": "Issue categories detected"},
            {"label": "Pipeline value", "value": "Blocked", "detail": "Dirty amount field", "tone": "warning"},
        ],
        "charts": [
            _chart("deal_volume_by_year", "Deal volume: current year vs previous year", [previous_label, year_label], [len(previous_deals), len(current_deals)], "Count of deals by created year."),
            _chart("won_deals_by_year", "Won deals: current year vs previous year", [previous_label, year_label], [len(previous_won), len(current_won)], "Count of deals whose status is WON."),
            _chart("deals_by_stage", "Deals by stage (raw labels)", list(stage_counts.keys()), list(stage_counts.values()), "Raw labels are preserved so casing and naming drift stays visible."),
            _chart("contacts_by_lifecycle", "Contacts by lifecycle stage", list(lifecycle_counts.keys()), list(lifecycle_counts.values()), "Raw contact count; duplicate identities are called out above."),
            _chart("activities_by_type", "Activities by type", list(activity_counts.keys()), list(activity_counts.values()), "Count of recorded CRM activities."),
        ],
        "comparisons": {"deal_volume": deal_change, "won_deals": won_change},
        "data_quality": {
            "duplicate_email_groups": duplicate_email_groups,
            "missing_amounts": missing_amounts,
            "comma_formatted_amounts": comma_amounts,
            "blank_close_dates": blank_close_dates,
            "stage_status_mismatches": stage_status_mismatches,
            "companies": len(companies),
            "activities": len(activities),
        },
        "insights": insights,
    }
