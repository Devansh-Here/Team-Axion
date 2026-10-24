# Demo script (synthetic data, local model)

Run from `backend/`: `python run_demo.py "<question>"`

| # | Question | Expected status | What to say |
|---|---|---|---|
| 1 | Total net sales by category in 2025 | ANSWER | Numbers come from the result rows. Warnings show missing markers (N/A, -) and ambiguous dates. |
| 3 | Which product had the biggest sales decline? | CLARIFICATION_REQUIRED | Absolute vs percent changes the answer, so it asks before calling the model. |
| 4 | What is the average employee salary by department? | APPROVAL_REQUIRED | Policy stops it before any protected data reaches the model. |
| 5 | Show the sales trend before 2020 | INSUFFICIENT_EVIDENCE | Profile shows data starts in 2024, so it abstains. |

## Not in this demo
- Q2 (categories lower in 2025 than 2024): the model's SQL was rejected by the guard on all 3 attempts, so the system abstained. Not reliable yet.
- Known bug: the guard's reject reason is not reaching the evidence pack (shows generic `sql_rejected`). To fix after the demo.

## Not measured / not run
- Accuracy: TBD. No-egress test: NOT RUN. Join-inflation check: not implemented. <=8B rule (D-01): open; Qwen2.5-Coder-7B is tentative.