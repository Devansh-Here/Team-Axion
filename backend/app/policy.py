"""Policy: kaun kya dekh sakta hai. Backend decide karta hai, client nahi.
Unknown role/dataset = DENY (fail closed).
Reason codes mein protected column ke naam kabhi nahi.

Built-in dataset ("demo"): CATALOG + PROTECTED_COLUMNS + ROLE_* tables.
Uploaded datasets: tables/columns file se aate hain (app.catalog). Sensitive-looking
column names (salary, email, phone, ...) automatically protected (fail closed).

Roles:
  viewer  - employees nahi, customer_name hidden, sales sirf Delhi region ki
  analyst - saari tables, customer_name hidden, salary -> ASK
  manager - saari tables, koi extra limit nahi, salary -> ASK
"""
import os
import re
import json
from pathlib import Path

from app import metadata_db

from app.catalog import load_dataset_catalog
from app.contracts import PolicyDecision

CATALOG = {
    "demo": {
        "sales": ["order_id", "order_date", "product_id", "region", "net_amt", "status"],
        "products": ["product_id", "product_name", "category"],
        "customers": ["customer_id", "customer_name", "region"],
        "employees": ["employee_id", "department", "salary"],
    }
}

# Kisi bhi role ko kabhi seedha nahi
PROTECTED_COLUMNS = {"employees.salary"}

# Table limit
ROLE_TABLES = {
    "viewer": {"sales", "products", "customers"},
    "analyst": {"sales", "products", "customers", "employees"},
    "manager": {"sales", "products", "customers", "employees"},
}

# Column limit (role-wise extra hidden columns, "table.column")
ROLE_DENY_COLUMNS = {
    "viewer": {"customers.customer_name"},
    "analyst": {"customers.customer_name"},
    "manager": set(),
}

# Row limit: role -> {table: (column, lowercase value)}
# NOTE: sirf policy batati hai. Enforce guard/executor me hota hai
# (table ko (SELECT * FROM t WHERE LOWER(col) = ?) se wrap karke).
ROLE_ROW_FILTERS = {
    "viewer": {"sales": ("region", "delhi")},
    "analyst": {},
    "manager": {},
}

# Jin roles ko protected data ke liye approval maangne ki ijazat hai (ASK).
# Baaki sab ko DENY.
ASK_ROLES = {"analyst", "manager"}

UPLOAD_ROLES = {"analyst"}

_PROTECTED_TERMS = re.compile(
    r"\b(salary|salaries|pay|payroll|wage|wages|compensation|earnings|earn|earns|"
    r"ctc|remuneration|stipend|bonus)\b", re.I
)
# Sirf uploaded datasets pe (aur sirf jab unme protected column ho)
_EXTRA_PROTECTED_TERMS = re.compile(
    r"\b(ssn|aadhaar|aadhar|passport|password|passwords|dob|birthdate|phone|"
    r"mobile|email|emails|cvv|iban)\b", re.I
)

_SENSITIVE_TOKENS = {
    "salary", "salaries", "wage", "wages", "payroll", "compensation", "ctc",
    "ssn", "aadhaar", "aadhar", "passport", "password", "passwd", "secret",
    "token", "apikey", "cvv", "iban", "dob", "phone", "mobile", "email", "emails",
}
_SENSITIVE_BIGRAMS = {
    ("credit", "card"), ("debit", "card"), ("card", "number"), ("card", "no"),
    ("account", "number"), ("account", "no"), ("api", "key"),
    ("date", "birth"), ("birth", "date"),
    ("pan", "number"), ("pan", "no"), ("pan", "card"),
}


def resolve_role() -> str:
    """Role server se aata hai, client se kabhi nahi."""
    return os.getenv("APP_ROLE", "analyst")


def can_upload(role: str) -> bool:
    return role in UPLOAD_ROLES


def _deny(code: str) -> PolicyDecision:
    return PolicyDecision(action="DENY", reason_code=code)


def _is_sensitive_name(column: str) -> bool:
    toks = [t for t in re.split(r"[^a-z0-9]+", str(column).lower()) if t]
    if any(t in _SENSITIVE_TOKENS for t in toks):
        return True
    return any((a, b) in _SENSITIVE_BIGRAMS for a, b in zip(toks, toks[1:]))


def _dataset_tables(dataset_id) -> dict[str, list[str]] | None:
    """Built-in CATALOG pehle. Uploaded datasets: file se."""
    if dataset_id in CATALOG:
        return CATALOG[dataset_id]
    return load_dataset_catalog(dataset_id) or None

_SNAP_CACHE: dict = {}


def _snapshot_hidden_names(dataset_id) -> set[str]:
    """Uploaded dataset: registration-time snapshot ke hisaab se extra hidden bare column names.
    Agar koi pehle wala sensitive column gayab hai (rename/drop), to snapshot me
    na-dikhne wale saare naye columns hidden. "*" = sab hidden (snapshot kharab = fail closed)."""
    try:
        dataset = load_dataset_catalog(dataset_id)
        row = metadata_db.get_dataset(dataset_id)
        if not dataset or not row:
            return set()
        dbp = Path(row["db_path"])
        f = dbp.with_name(dbp.name + ".protected.json")
        current = {c.lower() for cols in dataset.values() for c in cols}
        key = (str(f), frozenset(current))
        if key in _SNAP_CACHE:
            return set(_SNAP_CACHE[key])
        if f.is_file():
            snap = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(snap.get("protected"), list) or not isinstance(snap.get("known"), list):
                return {"*"}
        else:
            snap = {"protected": sorted(c for c in current if _is_sensitive_name(c)),
                    "known": sorted(current)}
            try:
                f.write_text(json.dumps(snap), encoding="utf-8")
            except Exception:
                pass                                   # write fail: is run ke liye memory snapshot
        missing = set(snap["protected"]) - current
        hidden = (current - set(snap["known"])) if missing else set()
        _SNAP_CACHE[key] = hidden
        return set(hidden)
    except Exception:
        return {"*"}


def is_protected(dataset_id, table: str, column: str) -> bool:
    if f"{table}.{column}" in PROTECTED_COLUMNS:
        return True
    if dataset_id in CATALOG:
        return False
    if _is_sensitive_name(column):
        return True
    extra = _snapshot_hidden_names(dataset_id)
    return "*" in extra or str(column).lower() in extra


def protected_column_names(dataset_id) -> set[str]:
    """Bare lowercase column names jo is dataset mein protected hain.
    API responses / profiles se strip karne ke liye (fail closed: naam se drop)."""
    names = {c.split(".", 1)[1].lower() for c in PROTECTED_COLUMNS}
    dataset = _dataset_tables(dataset_id)
    if dataset:
        for table, cols in dataset.items():
            for c in cols:
                if is_protected(dataset_id, table, c):
                    names.add(c.lower())
    return names


def hidden_column_names(role: str, dataset_id) -> set[str]:
    """Protected + is role ke liye hidden columns (bare lowercase naam).
    Output/evidence se strip karne ke liye use karo."""
    names = protected_column_names(dataset_id)
    if dataset_id in CATALOG:
        names |= {c.split(".", 1)[1].lower() for c in ROLE_DENY_COLUMNS.get(role, set())}
    return names


def strip_protected(obj, names: set[str]):
    """Kisi bhi nested dict/list se protected keys hata do."""
    if isinstance(obj, dict):
        return {k: strip_protected(v, names) for k, v in obj.items()
                if str(k).lower().split(".")[-1] not in names}
    if isinstance(obj, list):
        return [strip_protected(v, names) for v in obj]
    return obj


def permitted_schema(role: str, dataset_id: str) -> dict[str, list[str]]:
    tables = ROLE_TABLES.get(role)
    dataset = _dataset_tables(dataset_id)
    if tables is None or dataset is None:
        return {}
    builtin = dataset_id in CATALOG
    deny = ROLE_DENY_COLUMNS.get(role, set()) if builtin else set()
    out = {}
    for table, cols in dataset.items():
        if builtin and table not in tables:
            continue
        allowed = [c for c in cols
                   if not is_protected(dataset_id, table, c)
                   and f"{table}.{c}" not in deny]
        if allowed:
            out[table] = allowed
    return out


def row_filters(role: str, dataset_id: str) -> dict[str, tuple[str, str]]:
    """{table: (column, lowercase value)}. Guard/executor ye SQL pe lagayega."""
    if dataset_id not in CATALOG or role not in ROLE_TABLES:
        return {}
    return dict(ROLE_ROW_FILTERS.get(role, {}))


def _has_protected_columns(dataset_id) -> bool:
    dataset = _dataset_tables(dataset_id) or {}
    return any(is_protected(dataset_id, t, c) for t, cols in dataset.items() for c in cols)


def _mentions_protected(question: str, dataset_id) -> bool:
    if _PROTECTED_TERMS.search(question):
        return True
    return (dataset_id not in CATALOG
            and _has_protected_columns(dataset_id)
            and bool(_EXTRA_PROTECTED_TERMS.search(question)))


def authorize(role: str, dataset_id: str, question: str) -> PolicyDecision:
    try:
        if dataset_id not in CATALOG and not _dataset_tables(dataset_id):
            return _deny("UNKNOWN_DATASET")
        if role not in ROLE_TABLES:
            return _deny("UNKNOWN_ROLE")

        schema = permitted_schema(role, dataset_id)
        if not schema:
            return _deny("NO_PERMITTED_SCHEMA")

        if isinstance(question, str) and _mentions_protected(question, dataset_id):
            if role in ASK_ROLES:
                return PolicyDecision(action="ASK",
                                      reason_code="PROTECTED_DATA_APPROVAL_REQUIRED")
            return _deny("PROTECTED_DATA_DENIED")

        tables = set(schema)
        columns = {f"{t}.{c}" for t, cols in schema.items() for c in cols}
        return PolicyDecision(action="ALLOW", allowed_tables=tables,
                              allowed_columns=columns, reason_code="OK")
    except Exception:
        return _deny("POLICY_INTERNAL_ERROR")