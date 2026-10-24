from app.contracts import QueryOutcome


def execute_read_only(db_path: str, sql: str, params: list, *, timeout_s: float,
                      max_rows: int, max_bytes: int) -> QueryOutcome:
    # STUB: Kartik real read-only execution likhega
    return QueryOutcome(status="OK", columns=["category", "total"],
                        rows=[["Electronics", 1000.0]], row_count=1)