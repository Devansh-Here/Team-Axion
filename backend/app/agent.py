from app.contracts import AnalysisRequest, AnalysisOutcome


def analyze(request: AnalysisRequest, role: str) -> AnalysisOutcome:
    # STUB: Devansh real agent loop likhega
    return AnalysisOutcome(run_id="run_stub", status="INSUFFICIENT_EVIDENCE",
                           answer="stub response", warnings=["stub"])