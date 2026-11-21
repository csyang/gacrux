# Gacrux — Design Phases

Status legend: `[ ]` not started · `[~]` in progress · `[x]` complete

---

## Phase 0 — De-Risk Simulator Checkpoint Mechanism  ⭐ PRIORITY 0 (standalone)
*(Lives in `../checkpoint_mechanism_derisk/` — deliberately NOT part of the
Gacrux architecture. Answers one question before Spike B commits any
design effort to relying on it: does the simulator's native
checkpoint/restore mechanism reproduce identical downstream behavior,
including RNG state, after a restore?)*
- [x] Build standalone harness: trivial counter DUT + randomized-enable
      testbench (unrelated to the Gacrux FIFO, on purpose)
- [ ] Fill in exact `$save`/`$restart` syntax for the VCS version in use
- [ ] Fill in exact `checkpoint`/`restore` Tcl syntax for the QuestaSim
      version in use
- [ ] Run reference phase + restore phase, diff traces
- [ ] **Record result** (pass/fail, and any caveats such as "RNG state
      requires manual reseed") back into this doc before starting 1.2 in
      earnest
- [ ] If RNG state does NOT restore reliably: decide fallback — pin/log
      seed explicitly per test and re-derive, or restrict Phase 1 fault
      scenarios to ones that don't depend on live randomization during
      replay

**Result:** *(pending — fill in once the harness has been run against the
actual simulator versions in use)*

---

## Phase 1 — Proof of Concept

**Goal:** Prove checkpoint + restore works end-to-end, then extend to basic
backward stepping and binary search over checkpoints for fault
localization — across a pure-software track and two RTL tracks (SV/UVM-
optional testbench, and Python + cocotb), unified by a shared bisection
interface.

**Priority/sequencing:** Phase 0 (standalone, see above) runs first and is
a prerequisite for Spike B specifically. Within Phase 1 itself: Spike A
runs first as a fast, low-cost feasibility check on the core
checkpoint/bisection concept before committing effort to simulator-level
checkpointing. Spike B (SV/UVM) is the practical target and follows
immediately once Spike A de-risks the approach — this is the track that
matters most for day-to-day use. Spike C (cocotb) is lower priority for
this PoC and is deferred until after A and B are proven; it's not
required to hit the PoC objective, only useful for later comparison.

**Success criterion (all fault scenarios except FIFO_005 — see corpus
below):** bisection is considered correct if it converges to the
checkpoint interval `[C_n, C_n+1)` such that the fault predicate is false
at `C_n` and true at `C_n+1`, and the actual injected fault occurred
within that interval. This ties "correct" directly to checkpoint
granularity rather than an arbitrary N-step tolerance — the checkpoint
interval is the precision ceiling by construction, so there's no separate
judgment call about how close is close enough.

**Fault injection corpus:** a fixed set of 5 known-bad FIFO scenarios
(FIFO_001–005), implemented identically across Spike A and Spike B/C, is
defined in `../shared/fault_scenarios/CORPUS.md`. FIFO_005 is a
deliberate canary — it's non-monotonic by design, included to test what
the bisection engine does when its monotonicity assumption breaks, and is
exempt from the success criterion above.

### 1.0 — Shared Foundation
*(Needed before Spike A can be meaningfully tested — do this first)*
- [x] Define checkpoint metadata schema (JSON): index, timestamp, state
      pointer/path, optional predicate-eval cache
- [x] Define `evaluate_predicate(checkpoint_id) -> bool` interface
- [x] Implement shared bisection engine (binary search over checkpoint
      sequence, assumes monotonicity of fault manifestation)
- [x] Define fault injection corpus (5 scenarios, FIFO_001–005) —
      `shared/fault_scenarios/CORPUS.md`
- [ ] Unit tests for bisection engine against a mocked predicate
      (validated informally end-to-end against Spike A; formal pytest
      suite still pending)

### 1.1 — Spike A: General Software/Systems Track  ⭐ PRIORITY 1
*(Feasibility check — prove the core concept cheaply before committing to
simulator-level checkpointing)*
- [x] Build toy stateful Python process (circular-buffer FIFO model,
      mirroring RTL write_ptr/read_ptr/count structure so the shared
      fault corpus applies identically)
- [x] Serialization approach: **schema-based JSON** (resolved — see Open
      Decisions Log). Chosen over pickle for human-readability while
      state shape is still actively changing, and to avoid pickle's
      code-execution-on-load risk.
- [x] Implement checkpoint capture (`checkpoint_state()` → JSON file,
      including explicit RNG state, not just seed)
- [x] Implement restore-from-checkpoint (`restore_state()`, restores RNG
      state too)
- [x] Implement all 5 fault-corpus scenarios (FIFO_001–005) as scenario
      flags on `ToyProcess`
- [x] Wire into shared bisection engine — **validated end-to-end against
      all 5 corpus scenarios**, not just FIFO_001. Bisection correctly
      identified the earliest faulting checkpoint for FIFO_001–004; for
      FIFO_005 (canary), confirmed the predicate genuinely goes true then
      false again on a later checkpoint — i.e. it behaves non-monotonically
      exactly as designed, meaning bisection's result there is not
      meaningful without a monotonicity guard (tracked below).
- [x] **Determinism confirmation — RESOLVED.**
      `verify_seed_replay_determinism()` run across the no-fault baseline
      and all 5 fault scenarios: seed-only reconstruction reproduces full
      state identically in every case. For this Python model, seed alone
      is sufficient for deterministic replay, same as SV/UVM. Checkpoints
      still capture full `rng_state` regardless, as a safety net.
- [x] **Bug found and fixed during validation:** the reference/expected-
      behavior model wasn't enforcing FIFO capacity (would accept
      unlimited pushes, always return a value on pop), which silently
      masked FIFO_003 and FIFO_004 mismatches entirely — those two
      require deliberately stressing the full/empty boundary, and won't
      trigger under a generic push/pop sequence. Fixed; confirmed trigger
      sequences for all 5 scenarios now recorded in
      `shared/fault_scenarios/CORPUS.md`. Worth double-checking Spike B's
      scoreboard doesn't repeat the same oversight when porting the corpus
      to SV.
- [x] Implement backward stepping via restore + deterministic replay
      forward N steps. Implemented as `CheckpointedRun.goto_step()` in
      `spike_a_software/src/checkpointed_run.py`: checkpoints are sparse
      (not one per step), and any arbitrary step can be reconstructed by
      restoring the nearest earlier checkpoint and replaying logged
      actions forward. Validated against all 4 monotonic corpus scenarios
      with checkpoint_interval=3 — bisection correctly pinpointed the
      exact step, not just the nearest checkpoint, in every case.
- [x] **Bisection generalized to arbitrary steps, not just saved
      checkpoints:** added `find_earliest_fault_over_steps()` to
      `shared/bisection/engine.py`, since realistic checkpoint spacing
      means most steps won't have a saved checkpoint at all.
- [x] **Off-by-one bug found and fixed during this validation:** a run of
      N actions has N+1 addressable states (0..N inclusive, where state 0
      is "before any action"). Bisecting over N states instead of N+1
      silently drops the state after the final action — which is exactly
      the state FIFO_004 needs to trigger. Documented as a step-indexing
      convention in `shared/fault_scenarios/CORPUS.md`, with a regression
      test (`test_off_by_one_regression_full_run_state_is_reachable`).
- [x] **FIFO_005 failure mode sharpened, then addressed with an explicit
      guard:** with sparse checkpoints, plain fast-fail bisection silently
      reported "no fault found" for a run that did contain a real,
      transient fault — a silent false negative, not just an imprecise
      answer. **Monotonicity guard implemented** in
      `shared/bisection/engine.py` (`find_earliest_fault_over_steps()`
      now returns a `BisectionResult` with `.reliable` /
      `.monotonicity_violation_detected`):
        - **Default (free-ish):** records every point evaluated during
          the search, plus `guard_samples` (default 8) evenly-spaced
          upfront samples so the fast-fail path isn't relying on a single
          evaluated point. Flags a violation if any evaluated point
          contradicts monotonicity.
        - **Honest limitation, confirmed in testing, not just
          theoretical:** this is a probabilistic improvement, not a
          guarantee. With `guard_samples=8` on the FIFO_005 canary (11
          states), the sampling happened to land on step 9 and correctly
          caught the violation. With `guard_samples=2, 3, or 4` on the
          *exact same run*, it missed it entirely and reported
          `reliable=True` — wrongly. A transient fault landing between
          sampled points is invisible to this guard by construction; no
          amount of *fixed, cheap* sampling can guarantee catching an
          arbitrarily narrow transient blip.
        - **`full_scan=True` opt-in:** evaluates every step, guaranteed
          to catch any violation, at O(total_steps) cost instead of
          O(log total_steps + guard_samples). This is the only mode with
          an actual guarantee.
      Both the catch and the miss are captured as tests
      (`test_fifo_005_guard_catches_it_with_default_sampling`,
      `test_fifo_005_guard_can_still_miss_with_sparser_sampling`,
      `test_guard_can_miss_violation_with_sparse_sampling`) — the miss
      cases are kept as documented, expected behavior, not bugs to
      silently paper over.
- [x] Tests: formal pytest suite implemented —
      `spike_a_software/tests/test_toy_process.py`,
      `test_checkpointed_run.py`, `test_bisection_engine.py` (37 tests,
      all passing). Covers checkpoint/restore round-trip, seed-replay
      determinism, all 5 corpus scenarios, sparse-checkpoint bisection,
      the off-by-one regression, and both the guard's catch and its
      documented blind spot.

**Spike A status: feasibility confirmed.** The core concept — checkpoint,
restore, deterministic replay, and binary search to localize a fault to
an exact step using only sparse checkpoints — works end-to-end in
software. Remaining open item is a design decision (monotonicity guard),
not an implementation gap.

### 1.2 — Spike B: RTL Track (Traditional SV Testbench, UVM-optional)  ⭐ PRIORITY 2
*(The practical target — start immediately once Spike A confirms
feasibility, and once Phase 0's de-risk result is recorded)*
- [x] Build simple FIFO DUT (SystemVerilog)
- [x] Build plain SV testbench (driver/monitor/scoreboard, no UVM base
      classes required)
- [ ] Implement checkpoint capture via simulator-native mechanism
  - [ ] VCS: `$save` / `$restart`
  - [ ] QuestaSim: `checkpoint` / `restore` (Tcl)
- [ ] Implement all 5 fault-corpus scenarios (FIFO_001–005,
      `shared/fault_scenarios/CORPUS.md`) as `+define+`/force-based
      injections in the SV testbench
- [ ] Decide whether/when to grow the plain SV testbench into a full UVM
      environment (sequence/driver/monitor/scoreboard as UVM components)
- [ ] Define fault predicate (assertion violation or scoreboard mismatch)
- [ ] Wire into shared bisection engine
- [ ] Tests: checkpoint/restore round-trip in each simulator, bisection
      correctness on injected faults (all 5 scenarios)

*Determinism note:* explicit seeding always guarantees deterministic
replay in the SV/UVM environment — this is not an open question here the
way it is for Spike A. The main dependency is Phase 0's confirmation that
the simulator's checkpoint/restore mechanism actually preserves that RNG
state across a restore.

### 1.3 — Spike C: RTL Track (Python + cocotb)  — DEFERRED
*(Lower priority for this PoC; not required to hit the PoC objective —
pick up after A and B are proven, for later comparison)*
- [x] Build simple FIFO DUT (SystemVerilog) — shares design with Spike B
- [x] Build cocotb testbench
- [ ] Implement checkpoint capture via simulator-native mechanism
  - [ ] VCS: `$save` / `$restart`
  - [ ] QuestaSim: `checkpoint` / `restore` (Tcl)
- [ ] Implement Python orchestration layer: checkpoint bookkeeping,
      restore triggering, run management
- [ ] Define fault predicate (assertion violation or scoreboard mismatch)
- [ ] Wire into shared bisection engine
- [ ] Tests: checkpoint/restore round-trip in each simulator, bisection
      correctness on injected faults

### 1.4 — Integration & Comparison
- [ ] Run all three spikes against equivalent injected-fault scenarios
- [ ] Compare bisection results, checkpoint overhead (time/storage) across
      tracks
- [ ] Compare checkpoint/restore ergonomics between the SV-native testbench
      (Spike B) and the Python-orchestrated cocotb testbench (Spike C)
- [ ] Document divergences in approach forced by simulator vs. software
      constraints

### 1.5 — Stretch Goal
- [ ] Explore DPI-C-based checkpointing as a third approach
- [ ] Compare fidelity/performance against native simulator checkpoint
      commands

---

## Phase 2 — Scale-Up (not yet scoped)
- [ ] Extend DUT complexity: AXI4-Lite (following the FIFO → AXI4-Lite
      progression used elsewhere in the portfolio)
- [ ] Evaluate checkpoint interval strategy: fixed cadence vs.
      adaptive/on-event triggering
- [ ] Evaluate storage cost at scale; consider incremental/differential
      checkpointing
- [ ] Revisit monotonicity assumption in bisection (non-monotonic fault
      manifestation handling)

## Phase 3 — Tooling & Usability (not yet scoped)
- [ ] CLI or minimal UI for triggering bisection runs
- [ ] Reporting/visualization of checkpoint timeline and bisection path
- [ ] Documentation and worked example(s)

## Phase 4 — Write-up (not yet scoped)
- [ ] Conference-paper-style summary (consistent with prior portfolio
      projects, e.g. Edasich)
- [ ] Pitch deck / project summary artifact

---

## Open Decisions Log

| Decision | Options | Status |
|---|---|---|
| Checkpoint interval strategy | Fixed cadence (every N cycles) vs. adaptive/event-driven | Undecided — deferred to Phase 2 |
| Spike A serialization format | pickle (fast prototyping) vs. schema-based JSON/dict (portable) | **Resolved: schema-based JSON** — human-readable while state shape is still changing; avoids pickle's code-execution-on-load risk |
| DPI-C exploration | In scope as Phase 1 stretch goal, or pushed to Phase 2 | Currently: Phase 1 stretch |
| Spike A seed-only replay determinism | Confirmed (like SV/UVM) vs. requires full rng_state | **Resolved: confirmed.** Verified across no-fault baseline + all 5 fault scenarios; seed alone reproduces identical state. `rng_state` still captured as a safety net. |
| Simulator checkpoint RNG-state fidelity | Restores cleanly vs. requires manual reseed workaround | Pending Phase 0 result |
| Version control (git) | Initialize now vs. later | Deferred — will be added later, per Chris |
| Monotonicity guard for bisection engine | Leave as-is (silent wrong answer) vs. cheap probabilistic guard vs. full_scan | **Partially resolved — implemented, with an honest residual gap.** `find_earliest_fault_over_steps()` now returns a `BisectionResult` with `.reliable`. Default behavior adds `guard_samples` (default 8) upfront samples to catch violations for a small fixed cost; `full_scan=True` is an explicit opt-in that guarantees catching any violation at O(N) cost. Confirmed in testing that the default guard is a probabilistic improvement, NOT a guarantee — it caught the FIFO_005 canary at guard_samples=8 but missed the identical run at guard_samples=2-4. **Remaining open question:** what `guard_samples` default (or adaptive strategy, e.g. escalate to full_scan automatically whenever the default guard flags a violation, or when checkpoint intervals are known to be long relative to expected transient-fault duration) is appropriate once real cycle counts/checkpoint intervals from Spike B are known — a toy 11-state run and a multi-thousand-cycle simulation have very different sampling economics. |
