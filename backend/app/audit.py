"""Audit: SQL ka hash log hota hai, raw SQL/values nahi.
Whitelist fields only. Kabhi exception nahi uthata (audit fail != answer fail).
"""
import hashlib

from app import metadata_db

_ALLOWED_KEYS = {
    "run_id", "event_type", "dataset_id", "status", "policy_action",
    "reason_code", "exec_status", "row_count", "truncated", "elapsed_ms",
    "validation", "error_code", "repair_attempts", "model", "prompt_version",
}
_PROTECTED_WORDS = ("salary",)


def sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def _clean(value):
    if isinstance(value, str):
        low = value.lower()
        if any(w in low for w in _PROTECTED_WORDS):
            return "[REDACTED]"
        return value[:500]
    if isinstance(value, dict):
        return {str(k)[:100]: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value][:50]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:200]


def sanitize_event(event: dict) -> dict:
    out = {}
    for key in _ALLOWED_KEYS:
        if key in event:
            out[key] = _clean(event[key])
    sql = event.get("sql")
    if isinstance(sql, str) and sql.strip():
        out["sql_sha256"] = sql_hash(sql)  # hash only, raw SQL nahi
    return out


def write_audit_event(event: dict) -> None:
    try:
        clean = sanitize_event(event if isinstance(event, dict) else {})
        metadata_db.add_audit_event(
            clean.get("run_id"), str(clean.get("event_type", "event")), clean)
    except Exception:
        pass  # audit fail hone se pipeline nahi rukni chahiye