from dataclasses import dataclass


@dataclass
class Allow:
    ast: object = None


@dataclass
class Reject:
    reason: str


def validate_candidate(sql: str, allowed_tables: set[str], allowed_columns: set[str]):
    return Allow()  # STUB: Kartik real AST logic likhega