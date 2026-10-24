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
    assert deps.audits[0]["sql_hash"] and "SELECT" not in json.dumps(deps.audits[0])


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