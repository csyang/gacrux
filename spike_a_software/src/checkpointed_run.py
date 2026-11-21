"""
CheckpointedRun: manages a run of a ToyProcess with periodic (sparse)
checkpoints, and implements real backward stepping — restoring to the
nearest checkpoint at or before a target step, then deterministically
replaying forward to reach any arbitrary step in between.

This is the piece that makes Spike A a faithful proof of the Gacrux
concept rather than a toy case: checkpoints don't need to exist at every
step (that would defeat the purpose of checkpointing at all), and
bisection needs to be able to inspect ANY step, not just ones that
happen to have a saved checkpoint.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from spike_a_software.src.toy_process import ToyProcess
from shared.fault_scenarios.scenarios import FaultScenario


class CheckpointedRun:
    """Runs a ToyProcess, checkpointing every `checkpoint_interval` steps,
    while logging every action so that any intermediate step can be
    reconstructed via restore + replay.
    """

    def __init__(
        self,
        capacity: int = 8,
        fault_scenario: Optional[FaultScenario] = None,
        seed: Optional[int] = None,
        checkpoint_interval: int = 5,
        checkpoint_dir: str = "checkpoints",
    ):
        self.capacity = capacity
        self.fault_scenario = fault_scenario
        self.seed = seed
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_dir = checkpoint_dir
        os.makedirs(checkpoint_dir, exist_ok=True)

        self.process = ToyProcess(capacity=capacity, fault_scenario=fault_scenario, seed=seed)
        self.action_log: list[tuple[str, Optional[int]]] = []
        self.checkpoint_manifest: list[dict] = []

        # Always checkpoint the initial state (step 0), so goto_step(0) works
        # and every run has at least one restorable point.
        self._save_checkpoint(0)

    def step(self, action: str, value: Optional[int] = None) -> None:
        self.process.step(action, value)
        self.action_log.append((action, value))
        step_num = self.process.state.step_count
        if step_num % self.checkpoint_interval == 0:
            self._save_checkpoint(step_num)

    def _save_checkpoint(self, step_num: int) -> None:
        path = os.path.join(self.checkpoint_dir, f"ckpt_{step_num}.json")
        self.process.checkpoint_state(path)
        self.checkpoint_manifest.append({"step": step_num, "path": path})

    def nearest_checkpoint_at_or_before(self, target_step: int) -> dict:
        candidates = [c for c in self.checkpoint_manifest if c["step"] <= target_step]
        if not candidates:
            raise ValueError(f"No checkpoint exists at or before step {target_step}")
        return max(candidates, key=lambda c: c["step"])

    def goto_step(self, target_step: int) -> ToyProcess:
        """Return a fresh ToyProcess reconstructed at exactly `target_step`,
        via restore to the nearest earlier checkpoint + deterministic replay.

        Does not mutate self.process, so this is safe to call repeatedly
        (e.g. from a bisection search) without disturbing the live run.
        """
        ckpt = self.nearest_checkpoint_at_or_before(target_step)
        replay_proc = ToyProcess(capacity=self.capacity)
        replay_proc.restore_state(ckpt["path"])
        for step_idx in range(ckpt["step"], target_step):
            action, value = self.action_log[step_idx]
            replay_proc.step(action, value)
        return replay_proc

    @property
    def total_steps(self) -> int:
        return len(self.action_log)

    def save_manifest(self, path: str) -> None:
        """Persist the action log + checkpoint manifest, so a run can be
        reconstructed later without re-executing it."""
        with open(path, "w") as f:
            json.dump(
                {
                    "capacity": self.capacity,
                    "fault_scenario": self.fault_scenario.value if self.fault_scenario else None,
                    "checkpoint_interval": self.checkpoint_interval,
                    "action_log": self.action_log,
                    "checkpoints": self.checkpoint_manifest,
                },
                f,
                indent=2,
            )
