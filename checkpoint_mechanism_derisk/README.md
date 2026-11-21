# Checkpoint Mechanism De-Risk Harness

**This is intentionally NOT part of the Gacrux architecture.** It exists to
answer one question before any Gacrux code depends on the answer:

> Does the simulator's native checkpoint/restore mechanism
> (`$save`/`$restart` in VCS, `checkpoint`/`restore` in QuestaSim) actually
> reproduce identical downstream behavior after a restore — including RNG
> state — in our environment?

It uses a trivial free-running counter DUT, not the Gacrux FIFO, on
purpose. If this harness fails, it's telling you something about the
simulator/license/environment, not about Gacrux's design — and it's much
cheaper to find that out here than after Spike B's testbench is built.

## What it tests

1. **Basic round-trip** — run N cycles, save a checkpoint, keep running to
   N+100, save a full reference trace. Separately, restart from the saved
   checkpoint and run forward to N+100 again. Compare traces cycle-by-cycle.
2. **RNG state continuity** — the counter's increment is gated by a
   randomized enable signal (`$random`-driven), so any divergence between
   the original run and the restored run reveals whether the simulator
   restores RNG state as part of the checkpoint. This directly answers the
   open question flagged in Gacrux `docs/PHASES.md` about whether replay
   determinism can be trusted after restore.

## Pass/fail criterion

**Pass:** the restored run's trace is bit-identical to the original run's
trace for every cycle after the restore point.
**Fail:** any divergence — this must be understood and resolved (or
explicitly worked around, e.g. by re-seeding manually at each checkpoint)
before Gacrux Spike B commits to relying on native checkpoint/restore.

## Running

```
scripts/run_vcs.sh      # VCS
scripts/run_questa.sh   # QuestaSim
```

Both scripts run the two-phase experiment (original run + restored run)
and diff the resulting trace files in `results/`. See comments in each
script for where the actual `$save`/`$restart` or `checkpoint`/`restore`
calls need to be filled in with your simulator's exact syntax/version
requirements — these are scaffolded with the standard system
tasks/commands but may need site-specific adjustment.

## Outcome feeds back into Gacrux

Once this is resolved, record the result (pass/fail, and any caveats such
as "RNG state requires manual reseed") in
`../docs/PHASES.md` under Phase 0, before starting Spike B in earnest.
