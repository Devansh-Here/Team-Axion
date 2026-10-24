from app.contracts import QueryOutcome, ValidationReport


def validate_result(question: str, sql: str, outcome: QueryOutcome, profile: dict) -> ValidationReport:
    return ValidationReport(acceptable=True)  # STUB: Khushi likhegi