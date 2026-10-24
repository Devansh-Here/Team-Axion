# Evaluation results

## Status

The evaluation harness and fixed synthetic smoke cases are present. Full model evaluation is **TBD / NOT RUN**.

| Field | Value |
|---|---|
| Fixed smoke cases | 5 |
| Full benchmark size | TBD / NOT RUN |
| Real local model run | TBD / NOT RUN |
| Hosted model calls | None |
| Held-out split | TBD / NOT RUN |
| Hardware/runtime record | TBD / NOT RUN |

## Metrics

| Metric | Result |
|---|---|
| Execution accuracy | TBD / NOT RUN |
| Valid-SQL rate | TBD / NOT RUN |
| Repair success | TBD / NOT RUN |
| Abstention precision | TBD / NOT RUN |
| Abstention recall | TBD / NOT RUN |
| Median latency | TBD / NOT RUN |
| P95 latency | TBD / NOT RUN |

## Protocol

- Cases are stored in `outputs/evaluation_cases.json` with stable IDs and expected outcomes.
- The harness sorts case IDs deterministically and records the fixed seed.
- A runner must provide explicit fields for correctness, SQL validity, repair outcome, abstention and latency; missing fields are not inferred.
- Tuning and held-out evaluation sets must be separated before reporting benchmark metrics.
- The current five cases are a synthetic smoke set, not the planned 50–100 question benchmark.

The ablation template is tracked separately in `outputs/ABLATION.md`; all configurations are currently **TBD / NOT RUN**.

## Limitations

The real Ollama model/checkpoint, approved hardware record, benchmark protocol and full evaluation sample have not been run in this workspace. No accuracy or latency claim is made.
