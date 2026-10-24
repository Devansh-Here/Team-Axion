"""A3: Rule-based intent parsing + ambiguity detection. No LLM, no DB access."""
import re
from dataclasses import dataclass, field
from typing import Optional

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


@dataclass
class Ambiguity:
    term: str
    code: str
    question: str


@dataclass
class Intent:
    raw_question: str
    metric_terms: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    years: list[int] = field(default_factory=list)
    relative_period: Optional[str] = None   # e.g. "last year"
    comparison: bool = False
    top_n: Optional[int] = None
    trend: bool = False
    ambiguities: list[Ambiguity] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return bool(self.ambiguities)


METRIC_WORDS = ["net sales", "gross sales", "sales", "revenue", "profit", "salary", "amount", "orders", "count", "average", "total"]
RELATIVE_PERIODS = ["last year", "this year", "last quarter", "this quarter", "last month", "this month", "previous year"]
COMPARISON_WORDS = ["lower", "higher", "compared to", "versus", " vs ", "than last", "decline", "declined", "growth", "grew", "falling", "fell", "dropped", "increase", "decrease"]
TREND_WORDS = ["trend", "over time", "history", "historical", "before 20", "since 20"]


def parse_intent(question: str, confirmed_rules: Optional[dict[str, str]] = None) -> Intent:
    """confirmed_rules keys that silence a flag: 'fiscal_calendar', 'active_definition',
    'best_definition', 'profit_definition', 'falling_definition', 'decline_definition'."""
    rules = confirmed_rules or {}
    q = (question or "").strip()
    ql = " " + q.lower() + " "
    it = Intent(raw_question=q)

    it.metric_terms = [w for w in METRIC_WORDS if w in ql]
    it.years = sorted({int(m.group(0)) for m in YEAR_RE.finditer(ql)})
    it.relative_period = next((p for p in RELATIVE_PERIODS if p in ql), None)
    it.comparison = any(w in ql for w in COMPARISON_WORDS)
    it.trend = any(w in ql for w in TREND_WORDS)

    for m in re.finditer(r"\bby\s+([a-z_ ]+?)(?=\s+(?:in|for|during|since|before|after|than|where|and)\b|[?.,]|$)", ql):
        it.dimensions.append(m.group(1).strip())

    m = re.search(r"\b(?:top|bottom)\s+(\d+)\b", ql)
    if m:
        it.top_n = int(m.group(1))

    def flag(term: str, code: str, question: str, rule_key: str) -> None:
        if rule_key not in rules:
            it.ambiguities.append(Ambiguity(term, code, question))

    if it.relative_period:
        flag(it.relative_period, "AMBIGUOUS_PERIOD",
             f'Does "{it.relative_period}" mean the calendar period or the financial/fiscal period?',
             "fiscal_calendar")
    if re.search(r"\bprofit(able)?\b", ql):
        flag("profit", "UNDEFINED_METRIC", "How is profit defined (which revenue and cost columns)?", "profit_definition")
    if re.search(r"\bactive\b", ql) and not re.search(r"\bstatus\b", ql):
        flag("active", "UNDEFINED_TERM", 'What counts as "active" (which status value or rule)?', "active_definition")
    if re.search(r"\b(best|worst|top performing|best performing)\b", ql) and it.top_n is None:
        flag("best", "UNDEFINED_RANKING", 'What does "best" mean (which metric, and how many results)?', "best_definition")
    if re.search(r"\b(falling|declining|decline|declined|dropped|fell)\b", ql) and "decline_definition" not in rules and "falling_definition" not in rules:
        if re.search(r"\b(biggest|largest|most|highest)\b", ql):
            it.ambiguities.append(Ambiguity("biggest decline", "AMBIGUOUS_DECLINE",
                                            "Biggest decline in absolute amount or in percentage?"))
        # plain "lower than / falling" with explicit years is fine; with no years it is ambiguous
        elif not it.years:
            it.ambiguities.append(Ambiguity("falling", "UNDEFINED_TERM",
                                            "Which periods should be compared for the decline?"))
    return it