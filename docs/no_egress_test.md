# T-024 No-egress test

Status: **PARTIAL - offline boot, API smoke test and pytest done with the STUB agent; real agent + Ollama offline NOT RUN**

## Automated checks (pytest backend/tests/test_no_egress.py)
- Hosted SDK / telemetry imports in backend/app: PASS (test_no_hosted_sdk_imports)
- External URLs in code: PASS (test_no_external_urls_in_code, test_model_url_default_is_loopback)
- requirements.txt hosted packages: PASS (test_requirements_have_no_hosted_sdk)
- Blocked-socket run (guard, policy, executor, API): PASS (test_blocker_really_blocks, test_guard_policy_executor_work_offline, test_api_and_analyze_work_offline; analyze() is the stub agent)
- Result: 8 passed, 0 failed, 1 warning (Starlette/httpx TestClient deprecation)

## Manual offline run
- OS: Windows 11 Version 23H2 (OS Build 22631.9711), Python 3.12
- Date: 2026-10-25
- Method: Airplane mode ON (laptop was on Wi-Fi only). Ethernet: not used
- Network proof: `ping 8.8.8.8` -> General failure / Request timed out, Sent=4, Received=0, Lost=4 (100% loss)
- Executed on loopback only (127.0.0.1:8000) while ping was failing:
  - `uvicorn app.main:app --host 127.0.0.1 --port 8000` -> startup complete
  - GET /api/v1/health -> {"status":"ok"}
  - POST /api/v1/analyze -> HTTP 200, run_id=run_stub, status=INSUFFICIENT_EVIDENCE, answer="stub response" (Devansh stub, not the real agent)
  - `pytest -v` -> 127 passed, 0 failed, 1 warning (Starlette/httpx TestClient deprecation)
- Earlier runs with internet ON (ping 4/4 replies) are not counted as offline.
- Result: PASS for the items above

## Not verified
- NOT RUN: real analyze() with Ollama offline (agent/model not finished)
- NOT RUN: OS-level network namespace check (Windows has no `unshare`)
- /docs (Swagger UI) loads JS/CSS from a CDN in the browser; that is the browser, not an app egress.

Note: the automated check blocks non-loopback sockets inside Python only. It does not
replace a real offline run, and it does not prove other processes made no connections.