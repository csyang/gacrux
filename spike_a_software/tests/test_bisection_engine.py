"""
Unit tests for the shared bisection engine against a mocked predicate,
independent of any ToyProcess/checkpoint machinery. Covers the edge
cases flagged as pending in docs/PHASES.md 1.0, plus the monotonicity
guard's real, deliberately-not-oversold behavior.
"""

import pytest

from shared.bisection.engine import find_earliest_fault_over_steps
from shared.schema.checkpoint_schema import CheckpointRecord
from shared.bisection.engine import find_earliest_fault


def test_fault_never_manifests():
    result = find_earliest_fault_over_steps(10, lambda i: False)
    assert result.earliest_fault_step is None
    assert result.reliable is True


def test_fault_present_from_step_zero():
    result = find_earliest_fault_over_steps(10, lambda i: True)
    assert result.earliest_fault_step == 0
    assert result.reliable is True


def test_single_state_sequence():
    assert find_earliest_fault_over_steps(1, lambda i: True).earliest_fault_step == 0
    assert find_earliest_fault_over_steps(1, lambda i: False).earliest_fault_step is None


def test_fault_manifests_partway():
    # Predicate becomes true at step 6 and stays true (monotonic).
    def predicate(i):
        return i >= 6

    result = find_earliest_fault_over_steps(10, predicate)
    assert result.earliest_fault_step == 6
    assert result.reliable is True


def test_zero_length_run():
    result = find_earliest_fault_over_steps(0, lambda i: True)
    assert result.earliest_fault_step is None


# ----------------------------------------------------------------------
# Monotonicity guard — honest tests of what it actually catches and
# what it doesn't. See shared/bisection/engine.py module docstring.
# ----------------------------------------------------------------------

def test_guard_catches_violation_when_sample_lands_on_it():
    """With enough guard_samples to land on the transient True, the guard
    correctly flags the violation and reports the true earliest step."""

    def predicate(i):
        return i == 3  # true only transiently

    result = find_earliest_fault_over_steps(10, predicate, guard_samples=10)
    assert result.monotonicity_violation_detected is True
    assert result.reliable is False
    assert result.earliest_fault_step == 3


def test_guard_can_miss_violation_with_sparse_sampling():
    """Honest negative test: the guard is NOT a guarantee. With too few
    guard_samples to land on the single transient True, it is missed
    entirely and the result is reported as 'reliable' even though it
    isn't. This is a known, documented limitation — not a bug to fix
    silently. Only full_scan=True guarantees catching this."""

    def predicate(i):
        return i == 3  # true only transiently

    result = find_earliest_fault_over_steps(10, predicate, guard_samples=2)
    assert result.earliest_fault_step is None
    assert result.reliable is True  # wrong, but this is the documented blind spot


def test_full_scan_always_catches_transient_violation():
    """full_scan=True is the only mode that guarantees catching a
    transient (non-monotonic) fault, regardless of where it lands."""

    def predicate(i):
        return i == 3

    result = find_earliest_fault_over_steps(10, predicate, full_scan=True)
    assert result.monotonicity_violation_detected is True
    assert result.reliable is False
    assert result.earliest_fault_step == 3
    assert result.method == "full_scan"


def test_guard_does_not_false_positive_on_genuinely_monotonic_run():
    def predicate(i):
        return i >= 6

    result = find_earliest_fault_over_steps(20, predicate, guard_samples=8)
    assert result.monotonicity_violation_detected is False
    assert result.reliable is True
    assert result.earliest_fault_step == 6


# --- Legacy CheckpointRecord-based API (still used for the simple
# one-checkpoint-per-step case; does not carry the monotonicity guard) ---


def _make_records(n):
    return [
        CheckpointRecord(checkpoint_id=str(i), sequence_index=i, timestamp=float(i), state_path="", track="test")
        for i in range(n)
    ]


def test_checkpoint_record_api_basic():
    records = _make_records(8)

    def evaluate(record):
        return record.sequence_index >= 5

    result = find_earliest_fault(records, evaluate)
    assert result.sequence_index == 5


def test_checkpoint_record_api_empty_list():
    assert find_earliest_fault([], lambda r: True) is None
