# Team Axion — Complete Context for Claude

This is the shareable context file for the Hypnexis AI-02 hackathon project.
Read this file before making changes. Do not assume that the project is already
merged into `main`.

## User and repository

- User role: Kartik, working on Team Axion.
- User's local clone: `C:\Users\Kartik\Documents\GitHub\Team-Axion`
- App workspace clone: `D:\WEBdev\Terragotrail\TGT\Team-Axion`
- Remote: `https://github.com/Devansh-Here/Team-Axion.git`
- Current tested branch: `task01_kar/repo`
- Current tested revision: `5dcef4e docs(security): update lane c evidence`
- Target submission branch: `main`
- Devansh branch: `origin/feat/devansh-agent`, currently at `16346d0`
- Current date in this context: October 25, 2026.

The two filesystem paths above are different clones. Commands for the user
must use the `C:\Users\Kartik\...` path. The app workspace was clean before
the shareable-document files were created; the user's local clone separately
had an unfinished merge conflict.

## Project goal

Submit a tested integration of Lane A, Lane B and Lane C for the Hypnexis AI-02
hackathon. The final submission must be honest: do not invent accuracy,
latency, offline real-model, benchmark or ablation results.

## Completed implementation

### Lane C — Kartik

- SQL AST guard and read-only SQLite executor.
- Protected `employees.salary` handling in direct access, CTEs, aliases,
  subqueries, `WHERE`, `ORDER BY`, `HAVING`, `GROUP BY`, `UNION`, window
  functions and `CASE` expressions.
- Role/dataset authorization and fail-closed policy.
- Parameter binding, row/byte caps, timeout handling and safe API errors.
- Metadata DB, run/evidence persistence, audit events, SQL hashing and
  protected-text redaction.
- Loopback/no-egress checks.

Key commits:

- `e887d48 fix(sql-guard): block protected columns in clauses`
- `5dcef4e docs(security): update lane c evidence`

### Lane B — Khushi

- Profiler: `backend/app/profiler.py`
- Result checks: `backend/app/result_checks.py`
- CSV/XLSX ingestion: `backend/app/ingestion.py`
- Deterministic analytics: `backend/app/analytics.py`
- Evidence-first UI: `frontend/index.html`, `frontend/styles.css`,
  `frontend/app.js`
- Scenario helper: `backend/app/scenarios.py`
- Evaluation harness: `backend/app/evaluation.py`
- Fixed smoke cases: `outputs/evaluation_cases.json`
- Honest results: `outputs/RESULTS.md`
- Ablation template: `outputs/ABLATION.md`

Key commits:

- `9c24bbf feat(data-quality): add profiler and result checks`
- `185bd67 feat(ingestion): add safe csv and xlsx import`
- `92ad5c6 feat(analytics): add deterministic business metrics`
- `01c9cb8 feat(ui): add local evidence workspace`
- `89eb845 feat(evaluation): add honest benchmark harness`
- `7f885fb docs(evaluation): add ablation plan`
- `4388b35 feat(scenarios): add bounded what-if calculations`

### Lane A — Devansh branch

The remote Devansh branch contains model client, prompts, intent/schema linking,
agent loop, answer composition, wiring and demo-script work.

Relevant commits:

- `161c74b Lane A: model client, prompts, intent, schema linker, agent loop, evidence`
- `e3fa049 Lane A: wiring to real lanes, audit event alignment`
- `0f2cb48 Lane A: answer composition (A6), demo runner scripts`
- `e7cf083 Lane A: answer composition, demo runner scripts`
- `16346d0 docs: demo script (Q2 excluded, limitations listed)`

## Tests already run

Run from the `backend/` directory using the workspace virtual environment:

```powershell
"D:/WEBdev/Terragotrail/TGT/Team-Axion/.venv/Scripts/python.exe" -m pytest -q
```

Observed result: **235 passed, 1 warning**. The warning is the existing
Starlette/httpx `TestClient` deprecation. Do not weaken tests or change
unrelated dependencies to hide it.

Lane C focused command:

```powershell
"D:/WEBdev/Terragotrail/TGT/Team-Axion/.venv/Scripts/python.exe" -m pytest -q tests/test_sql_guard.py tests/test_executor.py tests/test_policy.py tests/test_api.py tests/test_audit.py tests/test_metadata_db.py tests/test_no_egress.py tests/test_prompts.py
```

Observed result: **143 passed, 1 warning**.

Scenario command:

```powershell
"D:/WEBdev/Terragotrail/TGT/Team-Axion/.venv/Scripts/python.exe" -m pytest -q tests/test_scenarios.py
```

Observed result: **6 passed**.

## Evidence and limitations

Security checklist: `docs/safe_sql_checklist.md`

No-egress record: `docs/no_egress_test.md`

The no-egress evidence is partial. Automated blocked-socket checks passed, but
the manual offline run used the stub agent. Real `analyze()` with Ollama while
offline has **not** been run.

Evaluation status in `outputs/RESULTS.md`:

- Five fixed synthetic smoke cases exist.
- Full 50–100 question benchmark: `TBD / NOT RUN`.
- Real local Ollama run: `TBD / NOT RUN`.
- Held-out split and hardware/runtime record: `TBD / NOT RUN`.
- Accuracy, valid-SQL rate, repair, abstention and latency: `TBD / NOT RUN`.
- All B8 ablation values: `TBD / NOT RUN`.

These must remain open until actually measured.

## User's merge conflict

The user ran this from the local clone:

```powershell
cd "C:\Users\Kartik\Documents\GitHub\Team-Axion"
git fetch origin
git switch task01_kar/repo
git pull --ff-only origin task01_kar/repo
git switch -c final/integration
git merge origin/feat/devansh-agent
```

`git switch -c final/integration` failed because the branch already exists.
The merge then ran on `task01_kar/repo` and produced conflicts in:

- `backend/app/profiler.py`
- `backend/app/result_checks.py`
- `backend/tests/test_profiler.py`
- `backend/tests/test_result_checks.py`

Safe recovery commands:

```powershell
cd "C:\Users\Kartik\Documents\GitHub\Team-Axion"
git merge --abort
```

Resolve conflicts by preserving the tested Lane B behavior while incorporating
newer Devansh changes. Do not use `git reset --hard`, delete branches, or
force-push. Inspect conflict markers first, then run tests.

## Final integration and submission plan

1. Abort the accidental merge on `task01_kar/repo`.
2. Switch to the existing `final/integration` branch.
3. Merge `origin/feat/devansh-agent`.
4. Resolve the four known conflicts.
5. Run the full backend test suite.
6. Run the live demo and smoke checks.
7. Commit and push `final/integration`.
8. Open a PR with base `main` and compare `final/integration`.
9. Review diff and checks before merging.
10. After merge, pull `main` and rerun the full tests.

## Live demo commands

In the user's local clone:

```powershell
cd "C:\Users\Kartik\Documents\GitHub\Team-Axion\backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Second PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
Invoke-RestMethod http://127.0.0.1:8000/api/v1/datasets
Invoke-RestMethod http://127.0.0.1:8000/api/v1/datasets/demo/profile
```

Expected health response contains `status: ok`. Do not present stub output as a
real Ollama result.

## Important decisions

- Use local loopback Ollama only; no hosted fallback.
- Keep protected fields out of schema, prompts, evidence and user output.
- Scenario outputs are assumption-only arithmetic, not causal forecasts.
- Keep existing Starlette/httpx warning accepted.
- Never claim `PASS`, `verified`, `offline`, accuracy or latency without a real
  executed check.
- Submit through a reviewable integration branch/PR, not a forceful rewrite of
  `main`.

## Shareable files created in the app workspace

- `docs/SESSION_HANDOFF.md` — detailed handoff.
- `docs/final_submission_handoff.html` — styled source for the PDF.
- `docs/final_submission_handoff.pdf` — polished handoff PDF.
- `docs/CLAUDE_CONTEXT.md` — this single-file context for Claude.

## Immediate next action

In the user's local clone, run `git merge --abort`, switch to the existing
`final/integration` branch, merge `origin/feat/devansh-agent`, inspect the four
conflicts, resolve them, and run the full tests. Do not say the project is on
`main` until the PR is actually reviewed and merged.
