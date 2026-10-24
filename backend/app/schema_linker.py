"""A4: Lexical schema linking with reasons + metric ambiguity detection. No LLM."""
import re
from dataclasses import dataclass, field
from typing import Optional

from app.intent import Intent

STOPWORDS = {"the", "a", "an", "of", "in", "by", "for", "to", "and", "or", "than", "which", "what", "had", "was",
             "were", "is", "are", "total", "show", "me", "all", "per", "with", "from", "that", "did", "do", "our"}

# question word -> column tokens it may refer to (kept small on purpose)
SYNONYMS = {
    "sales": {"amt", "amount", "revenue", "total", "sale"},
    "revenue": {"amt", "amount", "sales"},
    "net": {"net"},
    "gross": {"gross"},
    "category": {"cat", "category", "type"},
    "categories": {"cat", "category", "type"},
    "product": {"product", "prod", "item"},
    "products": {"product", "prod", "item"},
    "customer": {"customer", "cust", "client"},
    "customers": {"customer", "cust", "client"},
    "region": {"region", "area", "zone"},
    "date": {"date", "dt"},
    "orders": {"order", "orders"},
}

# generic metric words that need a net/gross/etc. qualifier to be unambiguous
GENERIC_METRIC_WORDS = {"sales", "revenue", "amount"}
MONEY_TOKENS = {"amt", "amount", "revenue", "total", "price"}
QUALIFIERS = {"net", "gross"}


@dataclass
class ColumnMatch:
    column: str          # "table.column"
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class LinkResult:
    matches: list[ColumnMatch] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    ambiguous_columns: list[str] = field(default_factory=list)


def _tokens(name: str) -> set[str]:
    parts = re.split(r"[^a-z0-9]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", name).lower())
    return {p for p in parts if p}


def _question_words(question: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", question.lower()) if w not in STOPWORDS]


def link_schema(
    intent: Intent,
    schema: dict[str, list[str]],
    allowed_columns: set[str],
    profile_facts: Optional[dict[str, str]] = None,
    confirmed_rules: Optional[dict[str, str]] = None,
) -> LinkResult:
    rules = confirmed_rules or {}
    allowed = {a.lower() for a in allowed_columns}
    words = _question_words(intent.raw_question)
    word_set = set(words)
    result = LinkResult()
    money_cols: list[tuple[str, set[str]]] = []

    for table, cols in schema.items():
        for col in cols:
            key = f"{table}.{col}"
            if key.lower() not in allowed:      # protected columns never ranked or mentioned
                continue
            col_tokens = _tokens(col)
            table_tokens = _tokens(table)
            score, reasons = 0.0, []
            for w in words:
                if w in col_tokens:
                    score += 2.0
                    reasons.append(f'"{w}" matches token in {key}')
                elif SYNONYMS.get(w, set()) & col_tokens:
                    score += 1.0
                    reasons.append(f'"{w}" is a synonym for a token in {key}')
                elif w in table_tokens:
                    score += 0.5
                    reasons.append(f'"{w}" matches table {table}')
            if profile_facts and key in profile_facts and score > 0:
                reasons.append(f"profile: {profile_facts[key]}")
            if score > 0:
                result.matches.append(ColumnMatch(key, score, reasons))
            if col_tokens & MONEY_TOKENS:
                money_cols.append((key, col_tokens))

    result.matches.sort(key=lambda m: (-m.score, m.column))

    # Metric ambiguity: generic "sales" word, no qualifier, several money columns
    if "metric_column" not in rules and (word_set & GENERIC_METRIC_WORDS) and not (word_set & QUALIFIERS):
        qualified = [k for k, toks in money_cols if toks & QUALIFIERS]
        if len(qualified) >= 2:
            result.needs_clarification = True
            result.ambiguous_columns = sorted(qualified)
            result.clarification_question = (
                "Which measure should I use: " + " or ".join(result.ambiguous_columns) + "?"
            )
    return result