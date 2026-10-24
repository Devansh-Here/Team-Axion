# Lane C - P0 tests and safe-SQL checklist (C8)

Owner: Kartik | Branch: task01_kar/repo (includes Devansh's feat/devansh-agent e3fa049)

## Run record
- Command: `pytest -q` (from `backend/`)
- Result: **194 passed, 0 failed, 1 warning** (Starlette/httpx TestClient deprecation)
- Machine: Windows 11 Version 23H2 (OS Build 22631.9711), Python 3.12.10
- Date: 2026-10-25
- Network state during this run: not recorded (do not cite as offline). The offline evidence is in `docs/no_egress_test.md` (127 passed, stub agent).

Legend: **PASS** = a named test passed in the run above. **TBD** = needs a check I have not seen. **NOT RUN** = not tested.
"PASS" is based on test names; the test bodies were not reviewed for this draft.

## 1. Unsafe SQL is rejected and the source DB is unchanged
| Item | Evidence | Status |
|---|---|---|
| DROP / UPDATE / DELETE / INSERT / CREATE / ALTER | `test_executor.py::test_attacks_blocked_and_db_unchanged[...]` | PASS |
| ATTACH DATABASE | same, `[ATTACH DATABASE ':memory:' AS m]` | PASS |
| PRAGMA writes (`writable_schema`, `journal_mode`) | same | PASS |
| `sqlite_master` access | same | PASS |
| `load_extension`, `randomblob` | same | PASS |
| Multi-statement (`SELECT 1; DROP TABLE sales`) | same | PASS |
| Comment-hidden statements | `test_rejected_statements[...; /* x */ DROP TABLE sales]`, `[...; -- c\nDROP TABLE sales]`, `test_allowed[... /* ; DROP TABLE sales */]` | PASS |
| Source DB hash unchanged after attacks | test name says "db_unchanged"; confirm the body compares a hash | TBD |
| Rejection happens before execution (guard first) | `test_sql_guard.py` (48 tests) | PASS (guard); order inside agent: see section 6 |

## 2. Protected columns are never exposed
| Item | Evidence | Status |
|---|---|---|
| Denied column in CTE / alias / subquery / WHERE / ORDER BY / scalar subquery / `SELECT *` / `s.*` | `test_denied_columns_and_star[...]` (11 cases) | PASS |
| Denied column in HAVING / GROUP BY / correlated subquery / UNION / window / CASE | no test yet | NOT RUN |
| Denied table (employees) via guard | `test_sql_guard.py::test_denied_tables_and_functions` | PASS |
| Salary stripped before prompt (permitted schema) | `test_policy.py::test_permitted_schema_strips_salary`, `test_salary_column_never_allowed` | PASS |
| Schema endpoint has no salary | `test_api.py::test_schema_has_no_salary` | PASS |
| Guard reject reason does not name columns | `test_sql_guard.py::test_reject_reason_never_leaks_column_names`, `test_policy.py::test_reason_codes_do_not_leak_column_names` | PASS |
| SQL errors do not leak raw messages | `test_executor.py::test_error_does_not_leak_raw_message` | PASS |
| Evidence has salary stripped | `test_api.py::test_evidence_roundtrip_and_salary_stripped` | PASS |
| Audit log: SQL hashed, protected text redacted | `test_audit.py::test_sql_is_hashed_not_stored`, `test_protected_text_redacted` | PASS |
| Profiles do not include protected fields | profile endpoint / profiler tests | NOT RUN |
| Protected column never in the LLM prompt | Devansh `test_prompts.py` (names not yet reviewed) | TBD |

## 3. Policy (role, dataset, fail closed)
| Item | Evidence | Status |
|---|---|---|
| Unknown role denied (`""`, `admin`, `root`, `None`, `ANALYST`) | `test_policy.py::test_unknown_role_denied[...]` | PASS |
| Unknown dataset denied | `test_policy.py::test_unknown_dataset_denied` | PASS |
| Non-string question does not crash | `test_policy.py::test_non_string_question_does_not_crash` | PASS |
| Salary question: analyst gets ASK, viewer gets DENY | `test_salary_question_analyst_is_ask_with_no_access`, `test_salary_question_viewer_is_deny` | PASS |
| Synonyms caught (payroll, wages, compensation, salaries) | `test_protected_terms_caught[...]` | PASS |
| Role is resolved server-side | `test_api.py::test_client_cannot_choose_role` | PASS |
| Demo Q4 end to end with the real agent | needs real agent + model | NOT RUN |

## 4. Executor limits
| Item | Evidence | Status |
|---|---|---|
| Params are bound; injection in a param is only a string | `test_params_are_bound`, `test_injection_in_param_is_just_a_string` | PASS |
| Row cap and byte cap set `truncated` | `test_row_cap_sets_truncated`, `test_byte_cap_sets_truncated` | PASS |
| Million-row result is capped | `test_million_row_result_is_capped` | PASS |
| Huge cross join times out | `test_huge_cross_join_times_out` | PASS |
| Missing DB gives a safe error | `test_missing_db_is_safe_error` | PASS |

## 5. API and metadata
| Item | Evidence | Status |
|---|---|---|
| Errors are safe (no stack, no paths) | `test_internal_error_leaks_nothing`, `test_schema_unknown_dataset_is_safe_404`, `test_missing_fields_safe_422`, `test_unknown_run_404` | PASS |
| Input validation | `test_bad_question_rejected[...]`, `test_audit_limit_validated` | PASS |
| Runs saved | `test_analyze_ok_and_run_saved` | PASS |
| Metadata SQL is parameterised | `test_metadata_db.py::test_sql_injection_in_values_is_just_text` | PASS |
| Audit never raises, pagination clamped | `test_audit.py::test_never_raises_*`, `test_metadata_db.py::test_audit_limit_is_clamped` | PASS |
| API binds to 127.0.0.1 | started manually with `--host 127.0.0.1` during the offline run; no test enforces the default | TBD (manual only) |

## 6. Cross-lane checks
| Item | Evidence | Status |
|---|---|---|
| No code path executes SQL that skipped `validate_candidate` (Lane A acceptance) | needs a code review of `agent.py` / `wiring.py` | TBD |
| No hosted SDK, no external URLs, loopback model URL | `test_no_egress.py` (8 tests) | PASS |
| App boots and serves with internet off (stub agent) | `docs/no_egress_test.md` | PASS (stub only) |
| Real `analyze()` + Ollama offline | agent + model needed | NOT RUN |
| Hash-chained audit (T-021, stretch) | not built | NOT RUN |

## Out of Lane C (not in my 194 tests)
Profiler, result checks, ingestion (Khushi) have no test files in this branch.
Repair cap, abstention, evidence completeness (Devansh) have `test_agent.py`; names not yet reviewed.

## Known gaps to close
1. Review the guard test names for CTE / subquery / alias / `SELECT *` / comment cases.
2. Confirm `test_attacks_blocked_and_db_unchanged` compares a hash.
3. Check `agent.py` calls `validate_candidate` before every `execute_read_only`.
4. Re-run offline once Devansh's real agent and Ollama are ready.
