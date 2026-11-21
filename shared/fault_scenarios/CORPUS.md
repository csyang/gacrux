# Gacrux Fault Injection Corpus

Fixed set of 5 known-bad FIFO scenarios, implemented once per track
(Python for Spike A, SystemVerilog for Spike B/C), so bisection results
can be compared apples-to-apples across tracks against identical bugs.

Each scenario defines:
- **id** — stable identifier used in code/config across all tracks
- **description** — what the bug does
- **fault predicate** — the observable condition that makes
  `evaluate_predicate()` return True
- **monotonicity** — whether the fault, once triggered, remains true for
  all subsequent checkpoints (required by the current bisection engine),
  or whether it's intermittent (used as a canary — see FIFO_005 below)

## Scenarios

### FIFO_001 — Off-by-one write pointer
Write pointer increments twice on a single write, corrupting one slot;
a later read returns stale/wrong data.
**Predicate:** scoreboard mismatch (popped value != expected reference
value).
**Monotonicity:** Monotonic — once a slot is corrupted, the mismatch
persists through subsequent reads of that slot and any comparison
against the reference model diverges permanently from that point.

### FIFO_002 — Dropped write under back-to-back pushes
A push is silently dropped when `wr_en` is asserted on consecutive
cycles.
**Predicate:** FIFO occupancy (or scoreboard queue length) diverges from
the reference model's expected occupancy.
**Monotonicity:** Monotonic — once a write is dropped, the occupancy
counts remain divergent for the rest of the run.

### FIFO_003 — Full flag asserted one cycle late
Allows an overwrite of unread data when the FIFO is actually full.
**Predicate:** a write succeeds when the reference model says the FIFO
should have rejected it (data corruption follows).
**Monotonicity:** Monotonic once the overwrite occurs.

### FIFO_004 — Empty flag deasserted one cycle early
Allows a read of invalid/stale data before a write has landed.
**Predicate:** a read returns data that doesn't match any value pushed
so far.
**Monotonicity:** Monotonic once the invalid read occurs.

### FIFO_005 — Pointer wraparound bug (canary — intermittent)
Corruption appears only when write/read pointers wrap past the depth
boundary, and only for that wraparound event — not for every write/read
thereafter.
**Predicate:** scoreboard mismatch, but only around wraparound events;
the predicate may go True then False again on subsequent non-wraparound
checkpoints.
**Monotonicity:** **NOT monotonic.** Confirmed in testing (Spike A,
sparse-checkpoint validation): the predicate went true at step 9 then
false again by step 10 (final state). **Concrete failure mode observed:**
because the bisection engine's fast-fail path originally checked only
the final state's predicate, and that final state happened to be clean
again, bisection reported "no fault found" for a run that DID contain a
real fault — a silent false negative, not an imprecise answer.

**A monotonicity guard is now implemented** in
`shared/bisection/engine.py` (`BisectionResult.reliable` /
`.monotonicity_violation_detected`), with `full_scan=True` as an explicit
opt-in for a guaranteed answer. The default guard is a genuine
improvement but is honestly probabilistic, not a guarantee: it caught
this exact FIFO_005 run's violation with `guard_samples=8`, but missed
the identical run entirely with `guard_samples=2-4`. This scenario stays
in the corpus specifically to keep that limitation visible and tested
(see `test_fifo_005_guard_can_still_miss_with_sparser_sampling`), rather
than letting the guard's existence create false confidence.

## Confirmed trigger stimulus (Spike A, validated)

Each scenario's fault predicate only fires under specific stimulus —
notably, FIFO_003 and FIFO_004 require deliberately stressing the
full/empty boundary (they will NOT trigger under generic push/pop
sequences that never reach capacity or true emptiness). Confirmed
minimal sequences (capacity=4) that reliably trigger each:

- **FIFO_001:** push,push,pop,push,pop,pop
- **FIFO_002:** push,push,push,pop,pop,pop
- **FIFO_003:** 5 pushes with no intervening pop (must exceed capacity
  while genuinely full), then drain
- **FIFO_004:** fill to capacity, drain completely, then one MORE pop past
  empty (exposes stale buffer contents at the wrapped read pointer)
- **FIFO_005:** push to capacity, pop some, push again to force a pointer
  wraparound, then continue popping — confirmed non-monotonic in testing
  (predicate observed going true, then false again, on a later checkpoint)

**Important implementation note carried over from Spike A validation:**
the reference/expected-behavior model MUST itself enforce FIFO capacity
(reject pushes when full, return nothing when empty) to serve as a valid
comparison baseline — an early version of the Spike A reference model
didn't do this and silently masked the FIFO_003/FIFO_004 mismatches
entirely. Worth double-checking the Spike B/C scoreboard model doesn't
make the same mistake, since it's an easy one to repeat when porting the
same corpus to SV.

**Step-indexing convention (learned the hard way — worth porting
deliberately):** "step N" means the state *after* N actions/cycles have
been applied, where N=0 is the initial state before any action. A run of
N actions therefore has N+1 addressable states (0..N inclusive), not N.
Bisecting over N states of an N-action run silently drops the state after
the final action — exactly the state most likely to matter. Confirmed
this the hard way in Spike A: an off-by-one here caused FIFO_004's fault
(which only appears after the very last action) to be missed entirely.
When Spike B addresses simulation state by cycle count, use the same
inclusive convention.

## Track-specific implementation notes

- **Spike A (Python):** each scenario is a boolean flag/parameter on
  `ToyProcess` that alters `step()`'s behavior; `fault_present()` checks
  the corresponding predicate. See `spike_a_software/src/toy_process.py`.
- **Spike B (SV testbench) / Spike C (cocotb):** each scenario is a
  `+define+` (SV) or DUT parameter/force (cocotb) that injects the bug
  into the FIFO RTL or drives it via testbench forcing; the scoreboard
  check in the testbench serves as the predicate.

## Success criterion (applies to all 5 scenarios except FIFO_005)

Per the agreed PoC success criterion: bisection is considered correct if
it converges to the checkpoint interval `[C_n, C_n+1)` such that the
fault predicate is false at `C_n` and true at `C_n+1`, and the actual
injected fault occurred within that interval. FIFO_005 is exempt from
this pass/fail bar — see monotonicity note above.
