"""Deterministic request/data-boundary safety checks."""

import re


INSTRUCTION_ATTACK_PATTERNS = (
    r"ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions?",
    r"reveal\s+(?:the\s+)?(?:system|developer)\s+prompt",
    r"show\s+(?:me\s+)?(?:the\s+)?hidden\s+(?:prompt|instructions?)",
    r"act\s+as\s+(?:an?\s+)?(?:admin|root|developer|system)",
    r"override\s+(?:the\s+)?(?:policy|guard|permissions?)",
    r"exfiltrat(?:e|ion)|send\s+.*(?:email|url|webhook|internet)",
    r"drop\s+table|delete\s+from|update\s+.*\s+set|insert\s+into|attach\s+database",
    r"pragma\s+|load_extension|readfile\s*\(|writefile\s*\(",
)

_ATTACK_RE = re.compile("|".join(f"(?:{pattern})" for pattern in INSTRUCTION_ATTACK_PATTERNS), re.I)

BOUNDARY_ATTACK_PATTERNS = (
    r"\b(?:salary|salaries|payroll|wages?|compensation|earnings|ctc)\b",
    r"employees?\.salary|sqlite_(?:master|schema)",
    r"\b(?:bypass|restricted|protected|hidden)\b",
    r"\b(?:subquery|cte|union|window function)\b.*\b(?:bypass|expose|append|protected)",
    r"\b(?:database file|external webhook|internet|exfiltrate)\b",
)
_BOUNDARY_RE = re.compile("|".join(f"(?:{pattern})" for pattern in BOUNDARY_ATTACK_PATTERNS), re.I)


def contains_untrusted_instruction(text: str | None) -> bool:
    """Return true for instruction-like text that must never reach the model."""
    return bool(_ATTACK_RE.search(str(text or "")))


def is_boundary_attack(text: str | None) -> bool:
    """Classify known policy/guard attack cases for the Phase 2 suite."""
    return contains_untrusted_instruction(text) or bool(_BOUNDARY_RE.search(str(text or "")))


def sanitize_data_label(value: object, max_chars: int = 120) -> str:
    """Keep data labels printable; never treat them as prompt instructions."""
    text = str(value or "").replace("\x00", " ")
    return " ".join(text.split())[:max_chars]
