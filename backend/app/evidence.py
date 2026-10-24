"""A7: Evidence pack builder. Whitelist only: unknown trace keys are never stored."""
import uuid
from typing import Any, Callable, Optional

from app.prompts import PROMPT_VERSION

ALLOWED_KEYS = [
    "run_id", "dataset_id", "question", "status", "policy_action", "schema_hash",
    "sql", "assumptions", "checks", "warnings", "attempts", "rejections", "result_summary",
]


def build_evidence_pack(trace: dict, evidence_id: str, model_name: str) -> dict:
    pack: dict[str, Any] = {k: trace[k] for k in ALLOWED_KEYS if k in trace}
    pack["evidence_id"] = evidence_id
    pack["parameters"] = []                  # redacted: the agent binds no parameters
    pack["dataset_sha256"] = "TBD"           # not measured yet (hard rule 7)
    pack["model"] = {"name": model_name, "prompt_version": PROMPT_VERSION}
    pack["repair_attempts"] = max(0, int(trace.get("attempts", 1)) - 1)
    summary = pack.get("result_summary")
    if isinstance(summary, dict):            # preview only, never full rows
        pack["result_summary"] = {k: summary.get(k) for k in ("columns", "rows", "row_count", "truncated")}
    return pack


def make_evidence_saver(store: Callable[[str, str, dict], Any], model_name: str) -> Callable[[dict], Optional[str]]:
    """store = metadata_db.save_evidence. Returns a function matching Deps.save_evidence."""
    def save(trace: dict) -> Optional[str]:
        evidence_id = f"ev_{uuid.uuid4().hex[:12]}"
        store(evidence_id, trace["run_id"], build_evidence_pack(trace, evidence_id, model_name))
        return evidence_id
    return save