"""
Tests for CheckpointedRun: sparse checkpointing + restore/replay backward
stepping, and end-to-end bisection over arbitrary steps (not just steps
that happen to have a saved checkpoint). This is the realistic case for
Gacrux — checkpoints don't exist at every step.
"""

import pytest

from spike_a_software.src.checkpointed_run import CheckpointedRun
from shared.fault_scenarios.scenarios import FaultScenario
from shared.bisection.engine import find_earliest_fault_over_steps

CAPACITY = 4
SEED = 5
CHECKPOINT_INTERVAL = 3

TRIGGER_SEQUENCES = {
    FaultScenario.OFF_BY_ONE_WRITE_PTR: [
        ("push", 1), ("push", 2), ("pop", None), ("push", 3), ("pop", None), ("pop", None),
    ],
    FaultScenario.DROPPED_WRITE_BACK_TO_BACK: [
        ("push", 1), ("push", 2), ("push", 3), ("pop", None), ("pop", None), ("pop", None),
    ],
    FaultScenario.FULL_FLAG_LATE: [
        ("push", 1), ("push", 2), ("push", 3), ("push", 4), ("push", 5),
        ("pop", None), ("pop", None), ("pop", None), ("pop", None),
    ],
    FaultScenario.EMPTY_FLAG_EARLY: [
        ("push", 1), ("push", 2), ("push", 3), ("push", 4),
        ("pop", None), ("pop", None), ("pop", None), ("pop", None), ("pop", None),
    ],
}

# FIFO_005 handled separately below — it's the deliberate non-monotonic canary.
MONOTONIC_SCENARIOS = list(TRIGGER_SEQUENCES.keys())

FIFO_005_ACTIONS = [
    ("push", 1), ("push", 2), ("push", 3), ("push", 4), ("pop", None), ("pop", None),
    ("push", 5), ("push", 6), ("pop", None), ("pop", None),
]


def _num_states(run):
    """A run of N actions has N+1 addressable states (0..N inclusive) —
    see shared/fault_scenarios/CORPUS.md step-indexing convention. This
    is a regression guard for the off-by-one found during development:
    using run.total_steps directly (without +1) silently drops the final
    action's resulting state from the search space."""
    return run.total_steps + 1


@pytest.mark.parametrize("scenario", MONOTONIC_SCENARIOS)
def test_sparse_checkpoint_bisection_finds_exact_step(tmp_path, scenario):
    run = CheckpointedRun(
        capacity=CAPACITY,
        fault_scenario=scenario,
        seed=SEED,
        checkpoint_interval=CHECKPOINT_INTERVAL,
        checkpoint_dir=str(tmp_path),
    )
    for action, value in TRIGGER_SEQUENCES[scenario]:
        run.step(action, value)

    # Sanity: checkpoints really are sparse, not one per step.
    assert len(run.checkpoint_manifest) < run.total_steps + 1

    num_states = _num_states(run)

    def evaluate(step_idx):
        return run.goto_step(step_idx).fault_present()

    ground_truth = [evaluate(i) for i in range(num_states)]
    expected = next((i for i, v in enumerate(ground_truth) if v), None)

    result = find_earliest_fault_over_steps(num_states, evaluate)
    assert result.earliest_fault_step == expected
    assert result.reliable is True, "monotonic scenarios should not trip the guard"


def test_off_by_one_regression_full_run_state_is_reachable(tmp_path):
    """Regression test for the specific off-by-one bug found during
    development: bisecting over `run.total_steps` (instead of
    `run.total_steps + 1`) silently excludes the state after the final
    action, which is exactly the state FIFO_004 needs to trigger in this
    sequence."""
    run = CheckpointedRun(
        capacity=CAPACITY,
        fault_scenario=FaultScenario.EMPTY_FLAG_EARLY,
        seed=SEED,
        checkpoint_interval=CHECKPOINT_INTERVAL,
        checkpoint_dir=str(tmp_path),
    )
    for action, value in TRIGGER_SEQUENCES[FaultScenario.EMPTY_FLAG_EARLY]:
        run.step(action, value)

    buggy_result = find_earliest_fault_over_steps(
        run.total_steps, lambda i: run.goto_step(i).fault_present()
    )
    correct_result = find_earliest_fault_over_steps(
        run.total_steps + 1, lambda i: run.goto_step(i).fault_present()
    )

    assert buggy_result.earliest_fault_step is None, "expected the off-by-one call to miss the fault"
    assert correct_result.earliest_fault_step is not None, "expected the corrected call to find the fault"


def test_fifo_005_guard_catches_it_with_default_sampling(tmp_path):
    """With the default guard_samples, the upfront coarse sampling happens
    to land on step 9 (where FIFO_005's fault transiently manifests) for
    this specific run length, correctly flagging the violation and
    reporting the true earliest fault step. This demonstrates the guard's
    real value — but see test_fifo_005_guard_can_still_miss_with_sparser_sampling
    for why this is a probabilistic improvement, not a guarantee."""
    run = CheckpointedRun(
        capacity=CAPACITY,
        fault_scenario=FaultScenario.POINTER_WRAPAROUND,
        seed=SEED,
        checkpoint_interval=CHECKPOINT_INTERVAL,
        checkpoint_dir=str(tmp_path),
    )
    for action, value in FIFO_005_ACTIONS:
        run.step(action, value)

    num_states = _num_states(run)

    def evaluate(step_idx):
        return run.goto_step(step_idx).fault_present()

    result = find_earliest_fault_over_steps(num_states, evaluate)  # default guard_samples=8

    assert result.monotonicity_violation_detected is True
    assert result.reliable is False
    assert result.earliest_fault_step == 9


def test_fifo_005_guard_can_still_miss_with_sparser_sampling(tmp_path):
    """Honest limitation test: with fewer guard samples, the same run's
    transient fault is missed entirely and reported as reliable — proving
    the guard is a probabilistic improvement, not a guarantee. Only
    full_scan=True is guaranteed to catch this."""
    run = CheckpointedRun(
        capacity=CAPACITY,
        fault_scenario=FaultScenario.POINTER_WRAPAROUND,
        seed=SEED,
        checkpoint_interval=CHECKPOINT_INTERVAL,
        checkpoint_dir=str(tmp_path),
    )
    for action, value in FIFO_005_ACTIONS:
        run.step(action, value)

    num_states = _num_states(run)

    def evaluate(step_idx):
        return run.goto_step(step_idx).fault_present()

    sparse_result = find_earliest_fault_over_steps(num_states, evaluate, guard_samples=2)
    full_scan_result = find_earliest_fault_over_steps(num_states, evaluate, full_scan=True)

    assert sparse_result.earliest_fault_step is None  # missed it
    assert sparse_result.reliable is True  # wrongly confident — documented limitation

    assert full_scan_result.earliest_fault_step == 9  # full scan always catches it
    assert full_scan_result.reliable is False
