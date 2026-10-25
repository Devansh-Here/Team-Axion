"""Recover permitted analytical schema after safe table renames or splits."""

import sqlite3
from pathlib import Path

from app.policy import CATALOG, PROTECTED_COLUMNS, ROLE_DENIED_COLUMNS, ROLE_TABLES


TABLE_ALIASES = {
    "sales": {"sales", "orders", "transactions"},
    "products": {"products", "items", "product_catalog"},
    "customers": {"customers", "accounts", "clients"},
    "employees": {"employees", "staff", "people_ops"},
    "companies": {"companies", "accounts", "organizations"},
    "contacts": {"contacts", "people", "contact_core"},
    "deals": {"deals", "opportunities", "deal_core", "deal_financials"},
    "activities": {"activities", "touchpoints", "engagements"},
}

COLUMN_ALIASES = {
    "amount": {"amount", "deal_amount", "value", "pipeline_value"},
    "probability": {"probability", "win_probability", "confidence"},
    "company_id": {"company_id", "account_id", "organization_id"},
    "contact_id": {"contact_id", "person_id"},
    "deal_id": {"deal_id", "opportunity_id"},
}


def _tables(db_path: str) -> dict[str, list[str]]:
    path = Path(db_path).resolve()
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    try:
        names = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )]
        def quote(identifier: str) -> str:
            return '"' + identifier.replace('"', '""') + '"'

        return {
            name: [row[1] for row in connection.execute(f"PRAGMA table_info({quote(name)})")]
            for name in names
        }
    finally:
        connection.close()


def _column_matches(canonical: str, actual: str) -> bool:
    return actual.lower() == canonical.lower() or actual.lower() in COLUMN_ALIASES.get(canonical, set())


def recover_permitted_schema(db_path: str, role: str, dataset_id: str) -> dict[str, list[str]]:
    """Return actual table/column names that map to the governed catalog.

    Exact names win. If a canonical table is absent, renamed aliases are
    matched by column overlap; the CRM deals table may be split across
    deal_core and deal_financials and both parts are exposed read-only.
    Unknown tables are never surfaced.
    """
    canonical = CATALOG.get(dataset_id)
    role_tables = ROLE_TABLES.get(role)
    if not canonical or not role_tables:
        return {}
    actual = _tables(db_path)
    recovered: dict[str, list[str]] = {}

    for canonical_table, canonical_columns in canonical.items():
        if canonical_table not in role_tables:
            continue
        candidates = []
        for actual_table, actual_columns in actual.items():
            alias_ok = actual_table.lower() in TABLE_ALIASES.get(canonical_table, {canonical_table})
            matched = [
                column for column in actual_columns
                if any(_column_matches(expected, column) for expected in canonical_columns)
            ]
            if alias_ok and matched:
                candidates.append((actual_table, actual_columns, matched))
        if not candidates:
            continue

        exact = next((item for item in candidates if item[0].lower() == canonical_table.lower()), None)
        selected = [exact] if exact else candidates
        for actual_table, actual_columns, _ in selected:
            keep = []
            for column in actual_columns:
                canonical_column = next(
                    (expected for expected in canonical_columns if _column_matches(expected, column)),
                    None,
                )
                if canonical_column is None:
                    continue
                protected = f"{canonical_table}.{canonical_column}" in PROTECTED_COLUMNS
                denied = f"{dataset_id}.{canonical_table}.{canonical_column}" in ROLE_DENIED_COLUMNS.get(role, set())
                if not protected and not denied:
                    keep.append(column)
            if keep:
                recovered[actual_table] = sorted(set(keep), key=actual_columns.index)

    return recovered
