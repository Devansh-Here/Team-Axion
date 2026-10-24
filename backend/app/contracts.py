from pydantic import BaseModel
from typing import Any, Literal, Optional

Status = Literal["ANSWER", "CLARIFICATION_REQUIRED", "INSUFFICIENT_EVIDENCE",
                 "ACCESS_DENIED", "APPROVAL_REQUIRED"]

class AnalysisRequest(BaseModel):
    dataset_id: str
    question: str
    mode: str = "question_answering"
    # role yahan NAHI hai. Role server side se aata hai.

class PolicyDecision(BaseModel):
    action: Literal["ALLOW", "MASK", "ASK", "DENY"]
    allowed_tables: set[str] = set()
    allowed_columns: set[str] = set()   # format: "table.column"
    reason_code: str = ""

class QueryOutcome(BaseModel):
    status: Literal["OK", "REJECTED", "ERROR", "TIMEOUT"]
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    elapsed_ms: int = 0
    error_code: Optional[str] = None

class ValidationReport(BaseModel):
    acceptable: bool
    checks: list[dict] = []     # {"code": str, "status": "PASS|WARNING|BLOCKED", "detail": str}
    warnings: list[str] = []
    needs_clarification: bool = False

class AnalysisOutcome(BaseModel):
    run_id: str
    status: Status
    answer: Optional[str] = None
    result_summary: Optional[dict] = None
    warnings: list[str] = []
    evidence_id: Optional[str] = None