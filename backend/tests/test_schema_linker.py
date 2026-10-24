from app.intent import parse_intent
from app.schema_linker import link_schema

SCHEMA = {
    "sales": ["order_id", "order_date", "product_id", "region", "net_amt", "gross_amt", "status"],
    "products": ["product_id", "product_name", "category"],
    "employees": ["employee_id", "department", "salary"],
}
ALLOWED = {
    "sales.order_id", "sales.order_date", "sales.product_id", "sales.region", "sales.net_amt",
    "sales.gross_amt", "sales.status",
    "products.product_id", "products.product_name", "products.category",
    "employees.employee_id", "employees.department",      # salary NOT allowed
}


def link(q, schema=SCHEMA, allowed=ALLOWED, **kw):
    return link_schema(parse_intent(q), schema, allowed, **kw)


def test_net_sales_picks_net_amt_without_clarification():
    r = link("Total net sales by category in 2025")
    assert not r.needs_clarification
    top = r.matches[0]
    assert top.column == "sales.net_amt"
    assert top.reasons


def test_category_column_is_ranked_with_reason():
    r = link("Total net sales by category in 2025")
    cols = {m.column: m for m in r.matches}
    assert "products.category" in cols
    assert cols["products.category"].reasons


def test_generic_sales_with_net_and_gross_asks_clarification():
    r = link("What were total sales by region?")
    assert r.needs_clarification
    assert set(r.ambiguous_columns) == {"sales.net_amt", "sales.gross_amt"}
    assert "net_amt" in r.clarification_question


def test_confirmed_metric_silences_clarification():
    r = link("What were total sales by region?", confirmed_rules={"metric_column": "sales.net_amt"})
    assert not r.needs_clarification


def test_gross_qualifier_picks_gross():
    r = link("Total gross sales by region")
    assert not r.needs_clarification
    assert r.matches[0].column == "sales.gross_amt"


def test_single_money_column_no_clarification():
    schema = {"sales": ["order_id", "net_amt", "region"]}
    allowed = {"sales.order_id", "sales.net_amt", "sales.region"}
    r = link("What were total sales by region?", schema, allowed)
    assert not r.needs_clarification


def test_protected_column_never_ranked_or_in_reasons():
    r = link("Average employee salary by department")
    assert all("salary" not in m.column for m in r.matches)
    assert all("salary" not in reason.lower() for m in r.matches for reason in m.reasons)


def test_profile_facts_only_for_allowed_and_matched():
    facts = {"sales.net_amt": "3 missing markers", "employees.salary": "secret"}
    r = link("Total net sales", profile_facts=facts)
    text = " ".join(x for m in r.matches for x in m.reasons)
    assert "3 missing markers" in text
    assert "secret" not in text


def test_no_match_returns_empty_not_crash():
    r = link("zzz qqq")
    assert r.matches == []
    assert not r.needs_clarification