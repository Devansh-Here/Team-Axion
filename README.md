# Team-Axion

Evidence-first analytics workspace for the Hypnexis AI-02 project.

## Mock CRM integration

The app now registers a synthetic **`crm_demo`** dataset at startup. It is a
deliberately messy local SQLite fixture containing companies, contacts, deals,
and activities. It includes case-variant stages, missing and comma-formatted
amounts, mixed date formats, duplicate contact emails, blank close dates, and
stage/status mismatches so the demo exercises data-quality checks instead of
looking like a clean toy CRM.
It uses the existing server-side policy, schema linker, read-only SQL guard,
result checks, evidence persistence, and audit trail; there is no CRM write
endpoint or external network dependency.

Run the backend from `backend/`:

```powershell
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then select **Mock CRM (read-only)** in the workspace. Example questions:

- Total pipeline value by deal stage
- Which owner has the most won revenue?
- How many contacts are in each lifecycle stage?
- Which company has the largest open opportunity?

The API exposes the CRM through the existing read-only routes, for example
`GET /api/v1/datasets/crm_demo/schema`,
`GET /api/v1/datasets/crm_demo/profile`, and `POST /api/v1/analyze` with
`{"dataset_id":"crm_demo", "question":"..."}`. Queries that aggregate
deals after joining contacts also receive a `JOIN_INFLATION_RISK` warning.
