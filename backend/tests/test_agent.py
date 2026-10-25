import json
from types import SimpleNamespace

from app.agent import Deps, analyze
from app.contracts import AnalysisRequest, PolicyDecision, QueryOutcome, ValidationReport
from app.model_client import ModelUnavailable


class Allow:
    pass


class Reject:
    def __init__(self, code="column_not_allowed"):
        self.code = code


class Seq:
    """Returns items in order (last one repeats); Exceptions are raised. Records calls."""
    def __init__(self, *items):
        self.items, self.calls = list(items), []

    def __call__(self, *args):
        self.calls.append(args)
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, Exception):
            raise item
        return item


SCHEMA = {"sales": ["order_id", "order_date", "net_amt", "region"],
          "products": ["product_id", "category"],
          "employees": ["employee_id", "salary"]}
ALLOWED = {"sales.order_id", "sales.order_date", "sales.net_amt", "sales.region",
           "products.product_id", "products.category", "employees.employee_id"}
POLICY = PolicyDecision(action="ALLOW", allowed_tables={"sales", "products", "employees"},
                        allowed_columns=ALLOWED)
GOOD = json.dumps({"sql": "SELECT category, SUM(net_amt) FROM sales GROUP BY category",
                   "assumptions": ["calendar year"], "needs_clarification": False,
                   "clarification_question": None})
OK = QueryOutcome(status="OK", columns=["category", "total"], rows=[["A", 1.0]], row_count=1)
PASS = ValidationReport(acceptable=True)
Q = "Total net sales by category in 2025"


def make_deps(generate=None, guard=None, execute=None, validate=None, policy=POLICY,
              schema=SCHEMA):
    audits, evidences = [], []
    deps = Deps(
        authorize=lambda role, ds, q: policy,
        get_schema=lambda ds: schema,
        get_profile=lambda ds, tables: {},
        guard=guard or Seq(Allow()),
        execute=execute or Seq(OK),
        validate_result=validate or Seq(PASS),
        generate=generate or Seq(GOOD),
        audit=audits.append,
        save_evidence=lambda ev: (evidences.append(ev) or "ev_test"),
    )
    deps.audits, deps.evidences = audits, evidences
    return deps


def run(deps, q=Q):
    return analyze(AnalysisRequest(dataset_id="ds", question=q), "analyst", deps)


def test_happy_path_answer():
    deps = make_deps()
    out = run(deps)
    assert out.status == "ANSWER"
    assert out.run_id.startswith("run_")
    assert out.evidence_id == "ev_test"
    assert out.result_summary["columns"] == ["category", "total"]
    assert len(deps.execute.calls) == 1
    assert deps.guard.calls[0][0].startswith("SELECT")
    assert len(deps.audits) == 1
    assert deps.audits[0]["event_type"] == "analysis"
    assert deps.audits[0]["sql"].startswith("SELECT")   # raw SQL goes to audit.py, which stores only its hash


def test_deny_never_calls_model():
    deps = make_deps(policy=PolicyDecision(action="DENY", reason_code="X"))
    assert run(deps).status == "ACCESS_DENIED"
    assert deps.generate.calls == []


def test_ask_returns_approval_required():
    deps = make_deps(policy=PolicyDecision(action="ASK", reason_code="X"))
    assert run(deps).status == "APPROVAL_REQUIRED"
    assert deps.generate.calls == []


def test_unknown_policy_action_fails_closed():
    weird = SimpleNamespace(action="WEIRD", allowed_tables={"sales"}, allowed_columns=ALLOWED)
    deps = make_deps(policy=weird)
    assert run(deps).status == "ACCESS_DENIED"
    assert deps.generate.calls == []


def test_authorize_exception_fails_closed():
    deps = make_deps()

    def boom(*a):
        raise RuntimeError("policy crashed")

    deps.authorize = boom
    assert run(deps).status == "ACCESS_DENIED"
    assert deps.generate.calls == []


def test_ambiguous_intent_clarifies_without_model():
    deps = make_deps()
    out = run(deps, "Which categories had falling sales last year?")
    assert out.status == "CLARIFICATION_REQUIRED"
    assert deps.generate.calls == []


def test_ambiguous_metric_clarifies_without_model():
    schema = {"sales": ["order_id", "region", "net_amt", "gross_amt"]}
    allowed = {"sales.order_id", "sales.region", "sales.net_amt", "sales.gross_amt"}
    policy = PolicyDecision(action="ALLOW", allowed_tables={"sales"}, allowed_columns=allowed)
    deps = make_deps(policy=policy, schema=schema)
    out = run(deps, "What were total sales by region?")
    assert out.status == "CLARIFICATION_REQUIRED"
    assert "net_amt" in out.answer
    assert deps.generate.calls == []


def test_malformed_json_then_valid_succeeds():  # T-014
    deps = make_deps(generate=Seq("not json", GOOD))
    out = run(deps)
    assert out.status == "ANSWER"
    assert len(deps.generate.calls) == 2
    assert "malformed_model_json" in deps.generate.calls[1][0]


def test_malformed_json_exhausted_never_executes():  # T-014
    deps = make_deps(generate=Seq("nope"))
    out = run(deps)
    assert out.status == "INSUFFICIENT_EVIDENCE"
    assert len(deps.generate.calls) == 3          # 1 candidate + 2 repairs, no more
    assert deps.execute.calls == []


def test_guard_rejection_never_executes_and_sql_not_fed_back():
    bad = json.dumps({"sql": "SELECT salary FROM employees", "assumptions": [],
                      "needs_clarification": False, "clarification_question": None})
    deps = make_deps(generate=Seq(bad), guard=Seq(Reject("column_not_allowed")))
    out = run(deps)
    assert out.status == "INSUFFICIENT_EVIDENCE"
    assert deps.execute.calls == []
    assert len(deps.generate.calls) == 3
    second_prompt = deps.generate.calls[1][0]
    assert "column_not_allowed" in second_prompt
    assert "salary" not in second_prompt.lower()
    assert "sql" not in deps.evidences[0]          # rejected SQL is not stored in evidence


def test_guard_non_allow_verdict_fails_closed():
    deps = make_deps(guard=Seq(object()))
    assert run(deps).status == "INSUFFICIENT_EVIDENCE"
    assert deps.execute.calls == []


def test_model_unavailable():  # T-015
    deps = make_deps(generate=Seq(ModelUnavailable("down")))
    out = run(deps)
    assert out.status == "INSUFFICIENT_EVIDENCE"
    assert "MODEL_UNAVAILABLE" in out.warnings
    assert deps.execute.calls == []


def test_execution_error_then_repair_succeeds():
    err = QueryOutcome(status="ERROR", error_code="no_such_column")
    deps = make_deps(execute=Seq(err, OK))
    out = run(deps)
    assert out.status == "ANSWER"
    assert len(deps.execute.calls) == 2
    assert "no_such_column" in deps.generate.calls[1][0]


def test_blocked_result_check_exhausts_repairs():
    blocked = ValidationReport(acceptable=False, checks=[{"code": "JOIN_INFLATION", "status": "BLOCKED", "detail": "x"}])
    deps = make_deps(validate=Seq(blocked))
    out = run(deps)
    assert out.status == "INSUFFICIENT_EVIDENCE"
    assert len(deps.generate.calls) == 3
    assert "JOIN_INFLATION" in deps.generate.calls[1][0]


def test_result_check_needs_clarification():
    rep = ValidationReport(acceptable=False, needs_clarification=True, warnings=["Which period do you mean?"])
    out = run(make_deps(validate=Seq(rep)))
    assert out.status == "CLARIFICATION_REQUIRED"
    assert out.answer == "Which period do you mean?"


def test_model_asks_clarification_without_executing():
    ask = json.dumps({"sql": "", "assumptions": [], "needs_clarification": True,
                      "clarification_question": "Absolute or percent?"})
    deps = make_deps(generate=Seq(ask))
    out = run(deps)
    assert out.status == "CLARIFICATION_REQUIRED"
    assert out.answer == "Absolute or percent?"
    assert deps.execute.calls == []

from app.agent import history_problem

P_2024 = {"sales": {"order_date": {"date_min": "2024-01-01", "date_max": "2024-12-31"}}}
P_LONG = {"sales": {"order_date": {"date_min": "2022-01-01", "date_max": "2025-12-31"}}}

def test_trend_before_2020_no_history():
    assert history_problem("sales trend before 2020", P_2024) == "NO_HISTORY_FOR_PERIOD"

def test_trend_snapshot_only():
    assert history_problem("sales trend over time", P_2024) == "SNAPSHOT_ONLY"

def test_trend_with_history_not_blocked():
    assert history_problem("sales trend 2022 to 2025", P_LONG) is None

def test_trend_unknown_profile_fails_closed():
    assert history_problem("sales trend", {}) == "NO_DATE_INFO"

def _trend_deps(profile):
    deps = make_deps()
    deps.get_profile = lambda ds, tables: profile
    return deps


def test_analyze_trend_no_history_abstains_without_model_call():  # T-018
    deps = _trend_deps(P_2024)
    out = analyze(AnalysisRequest(dataset_id="demo", question="sales trend before 2020"), "analyst", deps)
    assert out.status == "INSUFFICIENT_EVIDENCE"
    assert "NO_HISTORY_FOR_PERIOD" in out.warnings
    assert deps.generate.calls == []          # model was never called
    assert deps.guard.calls == []             # nothing executed


def test_analyze_trend_with_history_proceeds():
    deps = _trend_deps(P_LONG)
    out = analyze(AnalysisRequest(dataset_id="demo", question="sales trend 2022 to 2025"), "analyst", deps)
    assert out.status == "ANSWER"
    assert len(deps.generate.calls) == 1


def test_analyze_non_trend_ignores_history_check():
    deps = _trend_deps({})                    # empty profile must not block normal questions
    out = analyze(AnalysisRequest(dataset_id="demo", question=Q), "analyst", deps)
    assert out.status == "ANSWER"

from app.agent import compose_answer

def test_answer_numbers_come_from_rows_no_causal_words():
    o = QueryOutcome(status="OK", columns=["category", "total"],
                     rows=[["Electronics", 1200.5], ["Furniture", 350]], row_count=2)
    a = compose_answer(o)
    assert "Electronics" in a and "1,200.5" in a and "350" in a
    assert "Category" in a and "Total" in a and "Found 2 result(s)" in a
    assert not any(w in a.lower() for w in ("because", "due to", "caused by"))


def test_answer_formats_missing_values_and_multiple_rows():
    o = QueryOutcome(status="OK", columns=["lifecycle_stage", "contact_count"],
                     rows=[["Customer", 4], ["Lead", None]], row_count=2)
    a = compose_answer(o)
    assert "Lifecycle Stage: Customer" in a
    assert "Contact Count: 4" in a
    assert "Not available" in a

def test_real_guard_reject_reason_reaches_evidence_and_repair_prompt():
    """Regression: the real sql_guard.Reject exposes .reason (not .code). Test fakes used .code and hid the bug."""
    from app.sql_guard import validate_candidate
    bad = json.dumps({"sql": "DROP TABLE sales", "assumptions": [], "needs_clarification": False,
                      "clarification_question": None})
    good = json.dumps({"sql": "SELECT region, SUM(net_amt) FROM sales GROUP BY region", "assumptions": [],
                       "needs_clarification": False, "clarification_question": None})
    gen = Seq(bad, good)
    deps = make_deps(generate=gen, guard=validate_candidate)
    out = run(deps)
    assert out.status == "ANSWER"
    ev = deps.evidences[0]
    assert ev["rejections"] and ev["rejections"][0] != "sql_rejected"
    assert ev["rejections"][0] == "NOT_SELECT" or ev["rejections"][0].startswith("FORBIDDEN")
    assert ev["rejections"][0] in gen.calls[1][0]          # the repair prompt received the real reason


def test_evidence_dataset_hash_is_tbd_unless_measured():
    from app.evidence import build_evidence_pack
    assert build_evidence_pack({"run_id": "r"}, "ev_1", "m")["dataset_sha256"] == "TBD"
    assert build_evidence_pack({"run_id": "r"}, "ev_1", "m", "abc")["dataset_sha256"] == "abc"
