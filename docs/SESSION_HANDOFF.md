# Team Axion session handoff

## Goal

Prepare the Hypnexis AI-02 hackathon repository for final submission. The
intended end state is a tested, integrated branch containing Lane A, Lane B and
Lane C, followed by a reviewed merge/PR into `main`. The submission must be
honest about anything not actually measured: no invented accuracy, latency or
offline real-model claims.

## Repository and branch state

- App workspace repository: `D:\WEBdev\Terragotrail\TGT\Team-Axion`
- User's local PowerShell clone: `C:\Users\Kartik\Documents\GitHub\Team-Axion`
- Remote: `https://github.com/Devansh-Here/Team-Axion.git`
- Current app-workspace branch: `task01_kar/repo`
- Current app-workspace revision: `5dcef4e docs(security): update lane c evidence`
- `origin/task01_kar/repo` matches the current app-workspace branch.
- `main` / `origin/main` currently point to `d85c140` and are behind the
  integration work.
- `origin/feat/devansh-agent` currently points to `16346d0 docs: demo script
  (Q2 excluded, limitations listed)` and contains the latest Devansh Lane A
  commits that still need integration.

The app workspace was clean at handoff creation. This is separate from the
user's local clone: the user reported an in-progress merge conflict there.

## What was completed

### Lane C / Kartik

- SQL AST guard and read-only execution path.
- Protected-column handling, including `employees.salary` in direct access,
  CTEs, aliases, subqueries, `WHERE`, `ORDER BY`, `HAVING`, `GROUP BY`,
  `UNION`, window functions and `CASE` expressions.
- Policy checks for role, dataset and protected questions.
- Row/byte caps, timeout handling, parameter binding and safe errors.
- Metadata database, audit logging, SQL hashing and redaction.
- No-egress checks and loopback-only model URL checks.
- Security checklist updated in `docs/safe_sql_checklist.md`.

Important commits:

- `e887d48 fix(sql-guard): block protected columns in clauses`
- `5dcef4e docs(security): update lane c evidence`

### Lane B / Khushi

- Result checks: `backend/app/result_checks.py`
- CSV/XLSX ingestion: `backend/app/ingestion.py`
- Deterministic analytics: `backend/app/analytics.py`
- Static evidence-first UI: `frontend/index.html`, `frontend/styles.css`,
  `frontend/app.js`
- Scenario helper: `backend/app/scenarios.py`
- Evaluation harness: `backend/app/evaluation.py`
- Fixed smoke cases: `outputs/evaluation_cases.json`
- Honest evaluation report: `outputs/RESULTS.md`
- Ablation template: `outputs/ABLATION.md`

Important commits include:

- `9c24bbf feat(data-quality): add profiler and result checks`
- `185bd67 feat(ingestion): add safe csv and xlsx import`
- `92ad5c6 feat(analytics): add deterministic business metrics`
- `01c9cb8 feat(ui): add local evidence workspace`
- `89eb845 feat(evaluation): add honest benchmark harness`
- `7f885fb docs(evaluation): add ablation plan`
- `4388b35 feat(scenarios): add bounded what-if calculations`

### Lane A / Devansh currently available remotely

The remote Devansh branch includes model client, prompts, intent/schema linking,
agent loop, answer composition, wiring and demo-script work. Relevant remote
commits include:

- `161c74b Lane A: model client, prompts, intent, schema linker, agent loop, evidence`
- `e3fa049 Lane A: wiring to real lanes, audit event alignment`
- `0f2cb48 Lane A: answer composition (A6), demo runner scripts`
- `e7cf083 Lane A: answer composition, demo runner scripts`
- `16346d0 docs: demo script (Q2 excluded, limitations listed)`

## Verification already run

Run from `backend/` with the workspace virtual environment:

```powershell
"D:/WEBdev/Terragotrail/TGT/Team-Axion/.venv/Scripts/python.exe" -m pytest -q
```

Result: **235 passed, 1 warning** in about 10 seconds. The warning is the
existing Starlette/httpx `TestClient` deprecation; dependencies were not
changed to hide it.

Lane C focused command:

```powershell
"D:/WEBdev/Terragotrail/TGT/Team-Axion/.venv/Scripts/python.exe" -m pytest -q tests/test_sql_guard.py tests/test_executor.py tests/test_policy.py tests/test_api.py tests/test_audit.py tests/test_metadata_db.py tests/test_no_egress.py tests/test_prompts.py
```

Result: **143 passed, 1 warning**.

Scenario-only command:

```powershell
"D:/WEBdev/Terragotrail/TGT/Team-Axion/.venv/Scripts/python.exe" -m pytest -q tests/test_scenarios.py
```

Result: **6 passed**.

Earlier checks also established that the API served the UI and returned the
`demo` dataset/profile. The old result before later changes was `229 passed`;
do not use that stale number in current reporting.

## Current evidence and honest gaps

Detailed security mapping:

- `docs/safe_sql_checklist.md`

No-egress record:

- `docs/no_egress_test.md`

The no-egress document is explicitly partial: automated blocked-socket checks
passed, and the manual offline run used the **stub agent**. Real `analyze()`
with Ollama while offline has not been run.

Evaluation status in `outputs/RESULTS.md`:

- Fixed synthetic smoke cases: 5.
- Full 50–100 question benchmark: `TBD / NOT RUN`.
- Real local Ollama model run: `TBD / NOT RUN`.
- Held-out split and hardware/runtime record: `TBD / NOT RUN`.
- Accuracy, valid-SQL rate, repair, abstention and latency metrics:
  `TBD / NOT RUN`.
- All B8 ablation rows remain `TBD / NOT RUN`.

Do not change these to PASS without actual measured evidence.

## User's latest local merge problem

The user ran commands from:

```powershell
cd "C:\Users\Kartik\Documents\GitHub\Team-Axion"
git fetch origin
git switch task01_kar/repo
git pull --ff-only origin task01_kar/repo
git switch -c final/integration
git merge origin/feat/devansh-agent
```

The `git switch -c final/integration` command failed because that branch already
exists. Git then continued with the following merge on the current
`task01_kar/repo` branch, producing conflicts in:

- `backend/app/profiler.py`
- `backend/app/result_checks.py`
- `backend/tests/test_profiler.py`
- `backend/tests/test_result_checks.py`

The user was told not to commit during the conflict. The next safe action in
the user's local clone is:

```powershell
cd "C:\Users\Kartik\Documents\GitHub\Team-Axion"
git merge --abort
git status --short --branch
git switch final/integration
git status --short --branch
git merge origin/feat/devansh-agent
git status --short
git diff --name-only --diff-filter=U
```

If conflicts remain, resolve them by preserving the current tested Lane B
behavior while incorporating any genuinely newer Devansh changes. Do not use
`git reset --hard`, delete branches, or force-push. Inspect conflict markers
before editing and run the full test suite after resolution.

## Final integration plan

1. Recover the user's local clone with `git merge --abort` as above.
2. Merge `origin/feat/devansh-agent` into the existing `final/integration`
   branch, not directly into `task01_kar/repo`.
3. Resolve only the four known Lane B conflict files unless Git reports more.
4. Run the full backend test suite from `backend/`.
5. Start the live demo on loopback:

   ```powershell
   cd "C:\Users\Kartik\Documents\GitHub\Team-Axion\backend"
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

   Open `http://127.0.0.1:8000/`.

6. In a second PowerShell window, smoke-check:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/datasets
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/datasets/demo/profile
   ```

7. Review the demo script and ensure it does not present stub output as a real
   model result. Keep Q2 excluded/limitations as documented by `16346d0`.
8. Commit the resolved integration branch, push it, and open a PR with:
   - base: `main`
   - compare: `final/integration`
9. Review the PR diff and checks before merging to `main`.
10. After merge, verify `main` locally with `git pull origin main` and rerun the
    full tests from the merged commit.

## Submission/demo decisions

- Final submission should go through a reviewable integration branch/PR rather
  than a direct forceful main-branch rewrite.
- Keep the API on `127.0.0.1`; no hosted model/API fallback.
- Protected fields must stay out of prompts, evidence and user-visible schema.
- Scenario outputs are arithmetic assumption-only estimates, not causal
  forecasts; this is implemented and tested in `backend/app/scenarios.py`.
- Existing Starlette/httpx warning is accepted and should not be “fixed” by
  weakening tests or changing unrelated dependencies.
- The app is the user's coding assistant; the exact selected model is
  `gpt-6-astra` when identity is relevant.

## Next action

Start in the user's local clone by aborting the accidental merge on
`task01_kar/repo`, switch to the already-existing `final/integration` branch,
and re-run the merge there. Then inspect and resolve the four named conflicts
before running tests. Do not report the project as merged into `main` until the
integration branch passes tests and a reviewed PR is merged.
