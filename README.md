# Gacrux — Checkpointing & Reverse Debugging

**Source discipline:** Systems Software (process state checkpointing, reverse
debugging, and divide-and-conquer fault localization, drawn from OS/runtime
techniques such as CRIU, rr, and VM live migration)

**Named after:** Gacrux, the star at the top of the Southern Cross — a
navigation star. Fitting, since the binary search here navigates backward
through checkpoints to the origin of a fault.

## Concept

Gacrux saves the complete state of a running process at intervals
("checkpoints") so it can be restored later without re-running from scratch.
Reverse debugging extends this by stepping backward through execution via
restore + deterministic replay. Binary search over the checkpoint sequence
finds the earliest point at which a bug manifests, without requiring manual
re-runs with newly added probes.

## Structure

This project runs three spikes exploring the same core idea across
different environments, unified by a shared bisection interface.
**Sequencing for the PoC:** Phase 0 (standalone de-risk, below) runs
first, then Spike A runs as a fast feasibility check, Spike B (SV/UVM)
follows immediately as the practical target, and Spike C (cocotb) is
deferred to a lower priority — see `docs/PHASES.md` for the full
rationale.

```
gacrux/
├── checkpoint_mechanism_derisk/  # Standalone: de-risks $save/$restart and
│                                 # checkpoint/restore BEFORE any Gacrux
│                                 # code depends on them. Not part of the
│                                 # Gacrux architecture — see its own README.
├── spike_a_software/      # General software/systems track (pure Python)
│   ├── src/
│   ├── tests/
│   └── checkpoints/
├── spike_b_rtl_uvm/       # RTL track: traditional SV testbench (UVM-optional)
│   ├── rtl/
│   ├── tb/
│   ├── scripts/
│   └── checkpoints/
├── spike_c_rtl_cocotb/    # RTL track: Python + cocotb
│   ├── rtl/
│   ├── tb/
│   ├── scripts/
│   └── checkpoints/
├── shared/
│   ├── bisection/          # Common binary-search-over-checkpoints engine
│   ├── schema/              # Shared checkpoint metadata schema (JSON)
│   └── fault_scenarios/    # Fixed 5-scenario fault injection corpus
│                           # (FIFO_001–005), shared across all spikes
└── docs/
    └── PHASES.md          # Design phase tracking
```

### Phase 0 — Checkpoint Mechanism De-Risk (standalone, runs first)
A trivial free-running counter DUT, deliberately unrelated to the Gacrux
FIFO, used to confirm the simulator's native checkpoint/restore mechanism
actually reproduces identical downstream behavior — including RNG state
— after a restore, before Spike B commits any design effort to it. See
`checkpoint_mechanism_derisk/README.md`.

### Spike A — General Software/Systems Track (Priority 1: Feasibility Check)
A toy stateful Python process (software-model FIFO) stands in for the DUT.
State is checkpointed via serialization, restored, and stepped forward
deterministically to simulate "backward" debugging. Proves out the core
bisection algorithm cheaply before touching simulator complexity.

### Spike B — RTL Track: Traditional SV Testbench, UVM-optional (Priority 2: Practical Target)
A SystemVerilog FIFO DUT driven by a plain SystemVerilog testbench
(driver/monitor/scoreboard split, no UVM base classes required, though it
can grow into a full UVM environment later). This is the primary/default
verification approach in day-to-day use. Checkpointing uses simulator-
native mechanisms:
- **VCS:** `$save` / `$restart` system tasks
- **QuestaSim:** `checkpoint` / `restore` Tcl commands

### Spike C — RTL Track: Python + cocotb (Deferred)
The same FIFO DUT driven via a cocotb testbench, with checkpoint
orchestration handled from the Python side. Not required for the PoC
objective; picked up later, after Spikes A and B are proven, for
comparison purposes.

### Shared Stretch Goal
DPI-C-based checkpointing is deferred to the end of Phase 1 as an
exploratory comparison against native simulator checkpoint commands,
applicable to either RTL spike.

### Shared Core
Both spikes bisect against a common interface:

```python
def evaluate_predicate(checkpoint_id: str) -> bool:
    """Return True if the fault/condition of interest is present
    at this checkpoint."""
```

This lets the same binary-search engine walk either Python state snapshots
or simulator checkpoints without modification.

A fixed corpus of 5 known-bad FIFO scenarios (`shared/fault_scenarios/CORPUS.md`)
is implemented identically across all spikes, so bisection results can be
compared directly against the same injected bugs. One scenario (FIFO_005)
is a deliberate canary — non-monotonic by design — to test what happens
when the bisection engine's monotonicity assumption breaks.

## Status

See `docs/PHASES.md` for current phase and completion tracking.

## Organization-Agnostic Notice

This project is maintained as an independent, organization-agnostic
portfolio project. No employer-specific tooling, licenses, or proprietary
references are included.
