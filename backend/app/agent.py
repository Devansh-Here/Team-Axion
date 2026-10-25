"""A5: Agent orchestration. Model suggests; policy decides; guard validates; executor runs; checks verify."""
import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.contracts import AnalysisOutcome, AnalysisRequest, PolicyDecision, QueryOutcome, ValidationReport
from app.intent import parse_intent
from app.model_client import ModelUnavailable
from app.prompts import build_sql_prompt
from app.schema_linker import link_schema
from app.security import contains_untrusted_instruction
import re

def _iter_column_infos(profile):
    """Yield per-column profile dicts. Supports both profiler shapes:
    {table: {col: {...}}} (old) and {table: {"columns": {col: {...}}}} (data-quality lane)."""
    for table in (profile or {}).values():
        if not isinstance(table, dict):
            continue
        cols = table.get("columns") if isinstance(table.get("columns"), dict) else table
        for info in cols.values():
            if isinstance(info, dict):
                yield info


def _date_years(profile):
    mins, maxs = [], []
    for info in _iter_column_infos(profile):
        rng = info.get("date_range") if isinstance(info.get("date_range"), dict) else {}
        lo = info.get("date_min") or rng.get("min")
        hi = info.get("date_max") or rng.get("max")
        if lo and hi:
            try:
                mins.append(int(str(lo)[:4]))
                maxs.append(int(str(hi)[:4]))
            except ValueError:
                pass
    return mins, maxs


def history_problem(question, profile):
    """None if history is enough, else a reason code."""
    mins, maxs = _date_years(profile)
    if not mins:
        return "NO_DATE_INFO"
    lo, hi = min(mins), max(maxs)
    m = re.search(r"\b(?:before|until|till)\s+(\d{4})\b", question.lower())
    if m and lo >= int(m.group(1)):
        return "NO_HISTORY_FOR_PERIOD"
    if hi - lo < 1:
        return "SNAPSHOT_ONLY"
    return None

MAX_REPAIRS = 2          # 1 candidate + 2 repairs = 3 attempts max
PREVIEW_ROWS = 20


@dataclass
class Deps:
    authorize: Callable[[str, str, str], PolicyDecision]
    get_schema: Callable[[str], dict[str, list[str]]]       # dataset_id -> {table: [columns]}
    get_profile: Callable[[str, list[str]], dict]            # dataset_id, tables -> profile
    guard: Callable[[str, set, set], Any]                    # validate_candidate
    execute: Callable[[str, str, list], QueryOutcome]             # dataset_id, sql, params
    validate_result: Callable[[str, str, QueryOutcome, dict], ValidationReport]
    generate: Callable[[str], str]                           # ModelClient.generate
    audit: Callable[[dict], None]
    save_evidence: Optional[Callable[[dict], Optional[str]]] = None   # A7 fills this
    confirmed_rules: dict = field(default_factory=dict)


def _safe_code(value: Any, default: str) -> str:
    if not isinstance(value, str):
        return default
    return re.sub(r"[^A-Za-z0-9_]", "", value)[:60] or default


def _parse_model_json(raw: Any) -> Optional[dict]:
    """Strict parse. None = malformed."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    sql, nc = data.get("sql"), data.get("needs_clarification")
    cq, assumptions = data.get("clarification_question"), data.get("assumptions", [])
    if not isinstance(sql, str) or not isinstance(nc, bool):
        return None
    if cq is not None and not isinstance(cq, str):
        return None
    if not isinstance(assumptions, list) or not all(isinstance(a, str) for a in assumptions):
        return None
    if nc and not (cq and cq.strip()):
        return None
    if not nc and not sql.strip():
        return None
    return {"sql": sql, "needs_clarification": nc, "clarification_question": cq, "assumptions": assumptions}


def _display_column(column: str) -> str:
    """Turn SQL-style labels into labels a judge can scan quickly."""
    return re.sub(r"\s+", " ", str(column).replace("_", " ").strip()).title()


def _display_value(value: Any) -> str:
    """Format values without inventing units or changing their meaning."""
    if value is None:
        return "Not available"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value:,}"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "Not available"
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def compose_answer(outcome: QueryOutcome) -> str:
    """Create a readable, evidence-neutral answer from returned rows."""
    if outcome.row_count == 0:
        return "No rows matched the current filters."
    if outcome.row_count > 10:
        return f"Found {outcome.row_count:,} rows. See the result table below."

    lines = [f"Found {outcome.row_count:,} result(s):"]
    for row in outcome.rows:
        fields = " · ".join(
            f"{_display_column(column)}: {_display_value(value)}"
            for column, value in zip(outcome.columns, row)
        )
        lines.append(f"• {fields}")
    return "\n".join(lines)


def analyze(request: AnalysisRequest, role: str, deps: Optional[Deps] = None) -> AnalysisOutcome:
    if deps is None:
        from app.wiring import default_deps   # lazy import avoids circular import
        deps = default_deps(role)
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    trace: dict = {"run_id": run_id, "dataset_id": request.dataset_id, "question": request.question,
                   "attempts": 0, "rejections": [], "assumptions": [], "checks": []}

    def finish(status, answer=None, summary=None, warnings=None) -> AnalysisOutcome:
        warnings = list(warnings or [])
        trace.update(status=status, warnings=warnings, result_summary=summary)
        evidence_id = None
        if deps.save_evidence:
            try:
                evidence_id = deps.save_evidence(dict(trace))
            except Exception:
                warnings.append("EVIDENCE_NOT_SAVED")
        sql = trace.get("sql")
        try:
            deps.audit({
            "run_id": run_id, "event_type": "analysis", "dataset_id": request.dataset_id,
            "status": status, "policy_action": trace.get("policy_action"),
            "row_count": (summary or {}).get("row_count"),
            "repair_attempts": max(0, trace["attempts"] - 1),
            "error_code": trace["rejections"][-1] if trace["rejections"] else None,
            "sql": trace.get("sql"),          # audit.py hashes it; raw SQL is never stored
        })
        except Exception:
            pass  # audit failure must not crash or leak; Kartik's audit layer reports its own errors
        return AnalysisOutcome(run_id=run_id, status=status, answer=answer, result_summary=summary,
                               warnings=warnings, evidence_id=evidence_id)

    # 0. Prompt/data injection boundary: never send instruction-like text to the model.
    if contains_untrusted_instruction(request.question):
        trace["rejections"].append("UNTRUSTED_INSTRUCTION")
        return finish(
            "INSUFFICIENT_EVIDENCE",
            answer="I ignored instruction-like text and did not run it as a data request.",
            warnings=["UNTRUSTED_INSTRUCTION_IGNORED"],
        )

    # 1. Policy (fail closed)
    try:
        policy = deps.authorize(role, request.dataset_id, request.question)
        action = getattr(policy, "action", None)
    except Exception:
        policy, action = None, None
    trace["policy_action"] = action
    if action == "ASK":
        return finish("APPROVAL_REQUIRED", answer="This request needs approval before it can run.")
    if action not in ("ALLOW", "MASK") or not policy.allowed_columns:
        return finish("ACCESS_DENIED", answer="Access to the requested data is not permitted.")
    trace["row_limit"] = policy.row_limit
    trace["column_limit"] = policy.column_limit
    trace["schema_hash"] = hashlib.sha256(",".join(sorted(policy.allowed_columns)).encode()).hexdigest()[:16]

    # 2. Intent + schema linking (clarify BEFORE calling the model)
    intent = parse_intent(request.question, deps.confirmed_rules)
    if intent.needs_clarification:
        return finish("CLARIFICATION_REQUIRED", answer=intent.ambiguities[0].question)
    schema = deps.get_schema(request.dataset_id)
    link = link_schema(intent, schema, policy.allowed_columns, confirmed_rules=deps.confirmed_rules)
    if link.needs_clarification:
        return finish("CLARIFICATION_REQUIRED", answer=link.clarification_question)

    tables = sorted(policy.allowed_tables)
    profile = deps.get_profile(request.dataset_id, tables)
    if getattr(intent, "trend", False):
        reason = history_problem(request.question, profile)
        if reason:
            trace["rejections"].append(reason)
            return finish(
                "INSUFFICIENT_EVIDENCE",
                answer="The data does not contain enough history to answer this trend question.",
                warnings=[reason],
            )
    rules = [f"{k}: {v}" for k, v in deps.confirmed_rules.items()]

    # 3. Generate -> guard -> execute -> check (1 candidate + 2 repairs)
    previous_error: Optional[str] = None
    for attempt in range(1 + MAX_REPAIRS):
        trace["attempts"] = attempt + 1
        try:
            prompt = build_sql_prompt(request.question, schema, policy.allowed_columns,
                                      rules=rules or None, previous_error=previous_error)
        except ValueError:
            return finish("INSUFFICIENT_EVIDENCE", answer="The question could not be processed.",
                          warnings=["INVALID_QUESTION"])
        try:
            raw = deps.generate(prompt)
        except ModelUnavailable:
            return finish("INSUFFICIENT_EVIDENCE", answer="The local model is unavailable. Please retry.",
                          warnings=["MODEL_UNAVAILABLE"])

        parsed = _parse_model_json(raw)
        if parsed is None:
            previous_error = "malformed_model_json"
            trace["rejections"].append(previous_error)
            continue
        if parsed["needs_clarification"]:
            return finish("CLARIFICATION_REQUIRED", answer=parsed["clarification_question"])
        trace["assumptions"] = parsed["assumptions"]
        sql = parsed["sql"].strip()

        # Guard: nothing executes unless the verdict is exactly an Allow
        try:
            verdict = deps.guard(sql, policy.allowed_tables, policy.allowed_columns)
        except Exception:
            verdict = None
        if type(verdict).__name__ != "Allow":
            # sql_guard.Reject carries `.reason` (codes only, no column/table names); older stubs used `.code`
            reason = getattr(verdict, "reason", None) or getattr(verdict, "code", None)
            previous_error = _safe_code(reason, "sql_rejected")
            trace["rejections"].append(previous_error)   # rejected SQL itself is NOT stored
            continue

        trace["sql"] = sql
        outcome = deps.execute(request.dataset_id, sql, [])
        if outcome.status != "OK":
            previous_error = _safe_code(outcome.error_code, "execution_error")
            trace["rejections"].append(previous_error)
            continue

        if outcome.row_count > policy.row_limit:
            previous_error = "ROW_LIMIT_EXCEEDED"
            trace["rejections"].append(previous_error)
            continue
        if len(outcome.columns) > policy.column_limit:
            previous_error = "COLUMN_LIMIT_EXCEEDED"
            trace["rejections"].append(previous_error)
            continue

        report = deps.validate_result(request.question, sql, outcome, profile)
        trace["checks"] = report.checks
        if report.acceptable:
            warnings = list(report.warnings)
            if outcome.truncated:
                warnings.append("Result was truncated by the row/byte cap; totals are not complete.")
            summary = {"columns": outcome.columns, "rows": outcome.rows[:PREVIEW_ROWS],
                       "row_count": outcome.row_count, "truncated": outcome.truncated}
            return finish("ANSWER", answer=compose_answer(outcome), summary=summary, warnings=warnings)
        if report.needs_clarification:
            msg = report.warnings[0] if report.warnings else "More detail is needed to answer reliably."
            return finish("CLARIFICATION_REQUIRED", answer=msg)
        blocked = [c.get("code") for c in report.checks if c.get("status") == "BLOCKED"]
        previous_error = _safe_code(blocked[0] if blocked else None, "result_check_failed")
        trace["rejections"].append(previous_error)

    return finish("INSUFFICIENT_EVIDENCE", answer="I could not produce a safely validated answer for this question.",
                  warnings=["REPAIR_EXHAUSTED"])
