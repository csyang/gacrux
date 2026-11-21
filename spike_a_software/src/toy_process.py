"""
Toy stateful software process for Gacrux Spike A.

Stands in for a "DUT" in the general-software track: a circular-buffer
FIFO model (deliberately mirroring the RTL FIFO's write_ptr/read_ptr/count
structure, rather than a plain Python list) so the same fault-injection
corpus (shared/fault_scenarios/CORPUS.md) can be reproduced here and in
the RTL tracks for apples-to-apples bisection comparison.

Checkpointing uses schema-based JSON (not pickle): explicit, human-
readable, and stable across changes to this class's shape. See
docs/PHASES.md open-decisions log for the rationale.

Determinism note: this model uses an explicit RNG seed (matching the
SV/UVM convention of always having an explicit or simulator-assigned
seed). Whether *seed alone* is sufficient to guarantee deterministic
replay for this Python model (as it always is for the SV/UVM tracks) is
NOT yet confirmed — see verify_seed_replay_determinism() below and the
corresponding task in docs/PHASES.md 1.1.
"""

from __future__ import annotations

import json
import random
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

from shared.fault_scenarios.scenarios import FaultScenario


@dataclass
class ToyProcessState:
    """Full state of a ToyProcess instance, JSON-serializable as-is."""

    buffer: list = field(default_factory=list)       # circular buffer, len == capacity
    write_ptr: int = 0
    read_ptr: int = 0
    count: int = 0
    step_count: int = 0
    last_action: Optional[str] = None                # "push" | "pop" | None
    reference_queue: list = field(default_factory=list)  # bug-free reference model
    fault_scenario: Optional[str] = None              # FaultScenario value, or None
    fault_ever_detected: bool = False                 # sticky, for monotonic scenarios
    last_popped: Optional[int] = None                 # needed for FIFO_005's non-sticky predicate
    last_expected: Optional[int] = None
    seed: Optional[int] = None
    rng_state: Optional[list] = None                  # random.getstate(), JSON-encoded

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ToyProcessState":
        return cls(**data)


def _rng_state_to_jsonable(state: tuple) -> list:
    """random.getstate() returns (version, internal_state_tuple, gauss_next).
    internal_state_tuple is itself a tuple of ints; JSON needs lists."""
    version, internal_state, gauss_next = state
    return [version, list(internal_state), gauss_next]


def _rng_state_from_jsonable(data: list) -> tuple:
    version, internal_state, gauss_next = data
    return (version, tuple(internal_state), gauss_next)


class ToyProcess:
    """A minimal deterministic circular-buffer FIFO process.

    Mirrors the RTL FIFO's structure (write_ptr/read_ptr/count) closely
    enough that the shared fault-injection corpus (FIFO_001..FIFO_005)
    can be reproduced here in software terms.
    """

    def __init__(
        self,
        capacity: int = 8,
        fault_scenario: Optional[FaultScenario] = None,
        seed: Optional[int] = None,
    ):
        self.capacity = capacity
        self.fault_scenario = fault_scenario
        self.seed = seed if seed is not None else random.randrange(2**31)
        self.rng = random.Random(self.seed)
        self.state = ToyProcessState(
            buffer=[None] * capacity,
            fault_scenario=fault_scenario.value if fault_scenario else None,
            seed=self.seed,
        )
        self._reference: deque = deque()

    # ------------------------------------------------------------------
    # Stepping
    # ------------------------------------------------------------------

    def step(self, action: str, value: Optional[int] = None) -> None:
        """Advance by one step, applying the configured fault scenario (if any)."""
        s = self.state

        if action == "push":
            if len(self._reference) < self.capacity:
                self._reference.append(value)
            # else: a correct FIFO rejects the push; reference stays as-is.
            self._do_push(value, s)
        elif action == "pop":
            expected = self._reference.popleft() if self._reference else None
            s.last_expected = expected
            self._do_pop(s, expected)

        s.last_action = action
        s.step_count += 1
        s.reference_queue = list(self._reference)

        if self._check_fault(s):
            s.fault_ever_detected = True

    def _do_push(self, value, s: ToyProcessState) -> None:
        scenario = s.fault_scenario

        # FIFO_002: drop this write if the previous action was also a push.
        if scenario == FaultScenario.DROPPED_WRITE_BACK_TO_BACK.value and s.last_action == "push":
            return  # silently dropped

        is_full = s.count >= self.capacity
        # FIFO_003: full flag asserted one cycle late -> allow one extra push past capacity.
        allow_overwrite = scenario == FaultScenario.FULL_FLAG_LATE.value and s.count == self.capacity

        if is_full and not allow_overwrite:
            return  # correctly rejected

        s.buffer[s.write_ptr % self.capacity] = value

        # FIFO_001: off-by-one write pointer -> advances by 2, corrupting one slot.
        if scenario == FaultScenario.OFF_BY_ONE_WRITE_PTR.value:
            s.write_ptr = (s.write_ptr + 2) % self.capacity
        # FIFO_005: pointer wraparound bug -> extra +1 only at the wrap instant.
        elif scenario == FaultScenario.POINTER_WRAPAROUND.value and s.write_ptr == self.capacity - 1:
            s.write_ptr = (s.write_ptr + 2) % self.capacity  # corrupts just this one slot
        else:
            s.write_ptr = (s.write_ptr + 1) % self.capacity

        if not (is_full and allow_overwrite):
            s.count += 1
        # else: overwrite case — count stays the same, data corrupted instead.

    def _do_pop(self, s: ToyProcessState, expected) -> None:
        scenario = s.fault_scenario
        is_empty = s.count <= 0
        # FIFO_004: empty flag deasserted one cycle early -> allow a pop
        # even when logically empty, returning stale buffer contents.
        allow_early_read = scenario == FaultScenario.EMPTY_FLAG_EARLY.value and s.count == 0

        if is_empty and not allow_early_read:
            s.last_popped = None
            return

        s.last_popped = s.buffer[s.read_ptr % self.capacity]
        s.read_ptr = (s.read_ptr + 1) % self.capacity
        if not (is_empty and allow_early_read):
            s.count -= 1

    def _check_fault(self, s: ToyProcessState) -> bool:
        """Predicate: does the last pop's returned value match the reference model?"""
        if s.last_action != "pop":
            return False
        return s.last_expected != s.last_popped

    def fault_present(self) -> bool:
        """Whether the fault predicate is currently true.

        For monotonic scenarios (FIFO_001-004) this is sticky once tripped.
        For FIFO_005 (canary) this is intentionally NOT sticky — see
        shared/fault_scenarios/CORPUS.md.
        """
        if self.state.fault_scenario == FaultScenario.POINTER_WRAPAROUND.value:
            return self._check_fault(self.state)
        return self.state.fault_ever_detected

    # ------------------------------------------------------------------
    # Checkpoint / restore (schema-based JSON)
    # ------------------------------------------------------------------

    def checkpoint_state(self, path: str) -> None:
        """Write current state to a JSON file at `path`."""
        payload = self.state.to_dict()
        payload["rng_state"] = _rng_state_to_jsonable(self.rng.getstate())
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)

    def restore_state(self, path: str) -> None:
        """Restore state (including RNG state) from a JSON file at `path`."""
        with open(path) as f:
            payload = json.load(f)
        rng_state_data = payload.pop("rng_state", None)
        self.state = ToyProcessState.from_dict(payload)
        self._reference = deque(self.state.reference_queue)
        if rng_state_data is not None:
            self.rng.setstate(_rng_state_from_jsonable(rng_state_data))

    # ------------------------------------------------------------------
    # Determinism confirmation (see docs/PHASES.md 1.1 open question)
    # ------------------------------------------------------------------

    def verify_seed_replay_determinism(self, actions: list, capacity: Optional[int] = None) -> bool:
        """Confirm that re-running from just `self.seed` (a fresh instance,
        NOT a restored rng_state) reproduces this instance's current state
        after replaying `actions`.

        This answers the open question of whether seed-only reconstruction
        is sufficient for Spike A, the way it always is for SV/UVM. If this
        returns False, full rng_state (not just the seed) must be part of
        every checkpoint for replay to be trustworthy — which is already
        what checkpoint_state()/restore_state() do above, so this method is
        a confirmatory check, not a required dependency.
        """
        fresh = ToyProcess(
            capacity=capacity or self.capacity,
            fault_scenario=(
                FaultScenario(self.state.fault_scenario) if self.state.fault_scenario else None
            ),
            seed=self.seed,
        )
        for action, value in actions:
            fresh.step(action, value)
        return fresh.state.to_dict() == self.state.to_dict()
