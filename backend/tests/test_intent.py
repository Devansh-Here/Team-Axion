from app.intent import parse_intent


def codes(it):
    return {a.code for a in it.ambiguities}


def test_last_year_flagged_without_calendar():
    it = parse_intent("Which categories had falling sales last year?")
    assert it.needs_clarification
    assert "AMBIGUOUS_PERIOD" in codes(it)
    assert it.relative_period == "last year"


def test_last_year_not_flagged_when_calendar_confirmed():
    it = parse_intent("Total sales last year", confirmed_rules={"fiscal_calendar": "calendar year"})
    assert "AMBIGUOUS_PERIOD" not in codes(it)


def test_demo_q1_is_clear():
    it = parse_intent("Total net sales by category in 2025")
    assert not it.needs_clarification
    assert it.years == [2025]
    assert "net sales" in it.metric_terms
    assert it.dimensions == ["category"]


def test_demo_q2_explicit_years_not_ambiguous():
    it = parse_intent("Which categories had lower net sales in 2025 than 2024?")
    assert not it.needs_clarification
    assert it.years == [2024, 2025]
    assert it.comparison


def test_demo_q3_biggest_decline_needs_clarification():
    it = parse_intent("Which product had the biggest decline?")
    assert "AMBIGUOUS_DECLINE" in codes(it)


def test_profit_flagged_and_silenced_by_rule():
    assert "UNDEFINED_METRIC" in codes(parse_intent("What was our profit in 2025?"))
    assert not parse_intent("What was our profit in 2025?", {"profit_definition": "x"}).needs_clarification


def test_active_flagged():
    assert "UNDEFINED_TERM" in codes(parse_intent("How many active customers do we have?"))


def test_best_flagged_unless_top_n_given():
    assert "UNDEFINED_RANKING" in codes(parse_intent("Which is the best region?"))
    it = parse_intent("Top 5 regions by net sales in 2025")
    assert it.top_n == 5
    assert "UNDEFINED_RANKING" not in codes(it)


def test_trend_detected():
    it = parse_intent("Show the sales trend before 2020")
    assert it.trend
    assert it.years == [2020]


def test_falling_without_years_flagged():
    assert "UNDEFINED_TERM" in codes(parse_intent("Which categories are falling?"))


def test_empty_question_does_not_crash():
    it = parse_intent("")
    assert not it.needs_clarification