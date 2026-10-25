# Phase 2 safety report

## Scope

This report covers the Phase 2 extension: organization roles and limits,
instruction/data-boundary defenses, three-turn follow-up context, and schema
recovery after safe CRM table changes.

## Measured checks

| Check | Result | Meaning |
|---|---:|---|
| Attack boundary suite | **35 / 35 blocked before model** | Known instruction/policy/guard attack requests do not proceed as ordinary analysis requests. This is a boundary metric, not a claim of general model safety. |
| Follow-up context suite | **50 / 50 resolved** | The deterministic resolver preserved the prior question and applied the two follow-ups. This is context-resolution accuracy, not answer accuracy. |
| Schema recovery fixtures | **2 / 2 passed** | Recovery tests cover a renamed `deals` table (`opportunities`) and split deal tables (`deal_core` + `deal_financials`). |
| Full backend suite | **304 passed** | Existing regression suite plus Phase 2 tests. |

## Implemented controls

- `owner`, `analyst`, and `viewer` server-side roles.
- Per-role row and column limits; viewer cannot receive raw CRM contact emails.
- Protected-data approval remains fail-closed, including for the owner role.
- Instruction-like text is rejected before the model call.
- Prompts explicitly treat questions, schema identifiers, and data values as
  untrusted data; rows are never used as instructions.
- Conversation IDs persist three-turn follow-up context in the metadata DB.
- Schema discovery recovers safe table renames and split CRM deal tables without
  changing the model or retraining.

## How to reproduce

From `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

The report intentionally distinguishes deterministic safety/context metrics
from model answer accuracy. No unmeasured accuracy, latency, or causal claim is
included.
