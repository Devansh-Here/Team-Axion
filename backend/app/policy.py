"""Policy: kaun kya dekh sakta hai. Backend decide karta hai, client nahi.
Unknown role/dataset = DENY (fail closed).
Reason codes mein protected column ke naam kabhi nahi.
"""
import os
import re

from app.contracts import PolicyDecision

CATALOG = {
    "demo": {
        "sales": ["order_id", "order_date", "product_id", "region", "net_amt", "status"],
        "products": ["product_id", "product_name", "category"],
        "customers": ["customer_id", "customer_name", "region"],
        "employees": ["employee_id", "department", "salary"],
    }
}

PROTECTED_COLUMNS = {"employees.salary"}

ROLE_TABLES = {
    "analyst": {"sales", "products", "customers", "employees"},
    "viewer": {"sales", "products", "customers"},
}

_PROTECTED_TERMS = re.compile(
    r"\b(salary|salaries|pay|payroll|wage|wages|compensation|earnings|ctc)\b", re.I
)


def resolve_role() -> str:
    """Role server se aata hai, client se kabhi nahi."""
    return os.getenv("APP_ROLE", "analyst")


def _deny(code: str) -> PolicyDecision:
    return PolicyDecision(action="DENY", reason_code=code)


def permitted_schema(role: str, dataset_id: str) -> dict[str, list[str]]:
    tables = ROLE_TABLES.get(role)
    dataset = CATALOG.get(dataset_id)
    if tables is None or dataset is None:
        return {}
    out = {}
    for table, cols in dataset.items():
        if table not in tables:
            continue
        allowed = [c for c in cols if f"{table}.{c}" not in PROTECTED_COLUMNS]
        if allowed:
            out[table] = allowed
    return out


def authorize(role: str, dataset_id: str, question: str) -> PolicyDecision:
    try:
        if dataset_id not in CATALOG:
            return _deny("UNKNOWN_DATASET")
        if role not in ROLE_TABLES:
            return _deny("UNKNOWN_ROLE")

        schema = permitted_schema(role, dataset_id)
        if not schema:
            return _deny("NO_PERMITTED_SCHEMA")

        if isinstance(question, str) and _PROTECTED_TERMS.search(question):
            if role == "analyst":
                return PolicyDecision(action="ASK",
                                      reason_code="PROTECTED_DATA_APPROVAL_REQUIRED")
            return _deny("PROTECTED_DATA_DENIED")

        tables = set(schema)
        columns = {f"{t}.{c}" for t, cols in schema.items() for c in cols}
        return PolicyDecision(action="ALLOW", allowed_tables=tables,
                              allowed_columns=columns, reason_code="OK")
    except Exception:
        return _deny("POLICY_INTERNAL_ERROR")