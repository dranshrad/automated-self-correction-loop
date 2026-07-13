# Demo: fibonacci heal (mock provider)

This folder is a **checked-in** artifact walkthrough of one ASCL heal run:

**classify (`assertion`) → repair directive → pass**

No API keys required. Regenerated with:

```bash
bash scripts/regenerate_demo.sh
```

## Cycle at a glance

| Iteration | Outcome | Diagnosis |
|---|---|---|
| 1 | pytest failed | `failure_class=assertion` + repair hint |
| 2 | pytest passed | heal succeeds |

## Files

| File | Purpose |
|---|---|
| `metrics.json` | Run-level rich metrics |
| `report.json` | Full run + per-iteration taxonomy |
| `iteration_01/` | Failing candidate + classification |
| `iteration_02/` | Fixed candidate |
| `final_solution.py` | Last successful code |
| `command.sh` | Points back at the regenerate script |

See the [root README demo section](../../../README.md#demo-classify--repair--pass) and [terminal transcript](../../../docs/demo/heal-fibonacci.md).
