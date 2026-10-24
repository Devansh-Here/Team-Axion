# Ablation plan

This table is a measurement template, not a result claim. Every row must use
the same fixed cases, model checkpoint, hardware, seed and latency treatment.
Until Devansh's real local-model flow is ready, values remain **TBD / NOT RUN**.

## Configuration ladder

| Configuration | SQL generation context | Repair | Result checks / abstention | Execution accuracy | Valid-SQL rate | Median latency | P95 latency | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| One-shot baseline | Question only | No | No | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | Not measured |
| + schema/profile | Permitted schema + profile facts | No | No | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | Not measured |
| + repair/checks | Permitted schema + profile facts | Yes, bounded | Yes | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | Not measured |
| Final system | Final approved configuration | Yes, bounded | Yes | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | TBD / NOT RUN | Not measured |

## Measurement rules

- Use the same fixed case IDs from `outputs/evaluation_cases.json` or the later 50–100 question benchmark.
- Keep tuning cases separate from held-out evaluation cases.
- Report safety rejections separately from invalid SQL and semantic errors.
- Record warm/cold model treatment, hardware, model checkpoint and prompt version.
- Do not fill a metric from a smoke test or from model self-ratings.
- A configuration is not comparable if its case set, timeout, row cap or model runtime changes.

## Current status

The real Ollama run and the full benchmark are **TBD / NOT RUN**. No accuracy, latency or improvement claim is made.
