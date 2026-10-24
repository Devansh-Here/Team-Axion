from app.agent import analyze
from app.contracts import AnalysisRequest

while True:
    q = input("\nAsk > ").strip()
    if not q:
        break
    r = analyze(AnalysisRequest(dataset_id="demo", question=q), "analyst")
    print("STATUS  :", r.status)
    print("ANSWER  :", r.answer)
    for w in r.warnings:
        print("WARNING :", w)
    print("EVIDENCE:", r.evidence_id, "| RUN:", r.run_id)