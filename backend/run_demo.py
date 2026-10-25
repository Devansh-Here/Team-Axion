import json
import sys

from app.agent import analyze
from app.contracts import AnalysisRequest

q = " ".join(sys.argv[1:]) or "Total net sales by category in 2025"
r = analyze(AnalysisRequest(dataset_id="demo", question=q), "analyst")
print(json.dumps(r.model_dump(), indent=2, default=str))
