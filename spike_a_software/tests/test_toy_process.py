"""
Tests for ToyProcess: checkpoint/restore round-trip, seed-replay
determinism, and correctness of all 5 fault-corpus scenarios. Formalizes
the ad hoc validation scripts run during Spike A development.
"""

import json

import pytest

from spike_a_software.src.toy_process import ToyProcess
from shared.fault_scenarios.scenarios import FaultScenario

CAPACITY = 4
SEED = 123

# Confirmed minimal trigger sequences per scenario — see
# shared/fault_scenarios/CORPUS.md "Confirmed trigger stimulus".
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
    FaultScenario.POINTER_WRAPAROUND: [
        ("push", 1), ("push", 2), ("push", 3), ("push", 4), ("pop", None), ("pop", None),
        ("push", 5), ("push", 6), ("pop", None), ("pop", None),
    ],
}

NO_FAULT_ACTIONS = [("push", 1), ("push", 2), ("pop", None), ("pop", None)]


# ----------------------------------------------------------------------
# No-fault baseline
# ----------------------------------------------------------------------

def test_no_fault_case_stays_clean():
    p = ToyProcess(capacity=CAPACITY, seed=SEED)
    for action, value in NO_FAULT_ACTIONS:
        p.step(action, value)
    assert p.fault_present() is False


# ----------------------------------------------------------------------
# Each corpus scenario actually triggers its predicate
# ----------------------------------------------------------------------

# FIFO_005 is deliberately non-monotonic (see CORPUS.md) — its predicate
# is NOT guaranteed True at the final step, so it's excluded from this
# generic check and covered separately by test_fifo_005_is_non_monotonic.
MONOTONIC_SCENARIOS_FOR_FINAL_STATE_CHECK = [
    s for s in FaultScenario if s != FaultScenario.POINTER_WRAPAROUND
]


@pytest.mark.parametrize("scenario", MONOTONIC_SCENARIOS_FOR_FINAL_STATE_CHECK)
def test_scenario_triggers_fault(scenario):
    p = ToyProcess(capacity=CAPACITY, fault_scenario=scenario, seed=SEED)
    for action, value in TRIGGER_SEQUENCES[scenario]:
        p.step(action, value)
    assert p.fault_present() is True, f"{scenario.value} did not trigger its fault predicate"


# ----------------------------------------------------------------------
# Checkpoint / restore round-trip
# ----------------------------------------------------------------------

@pytest.mark.parametrize("scenario", list(FaultScenario))
def test_checkpoint_restore_round_trip(tmp_path, scenario):
    p = ToyProcess(capacity=CAPACITY, fault_scenario=scenario, seed=SEED)
    for action, value in TRIGGER_SEQUENCES[scenario]:
        p.step(action, value)

    ckpt_path = tmp_path / "checkpoint.json"
    p.checkpoint_state(str(ckpt_path))

    restored = ToyProcess(capacity=CAPACITY, seed=999)  # deliberately different seed
    restored.restore_state(str(ckpt_path))

    assert restored.state.to_dict() == p.state.to_dict()
    assert restored.fault_present() == p.fault_present()


def test_checkpoint_file_is_human_readable_json(tmp_path):
    p = ToyProcess(capacity=CAPACITY, seed=SEED)
    p.step("push", 42)
    ckpt_path = tmp_path / "checkpoint.json"
    p.checkpoint_state(str(ckpt_path))

    with open(ckpt_path) as f:
        data = json.load(f)  # must not raise — confirms it's plain JSON, not pickle
    assert "buffer" in data
    assert "rng_state" in data


# ----------------------------------------------------------------------
# Seed-replay determinism (resolved open question — see docs/PHASES.md)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("scenario", [None] + list(FaultScenario))
def test_seed_replay_determinism(scenario):
    p = ToyProcess(capacity=CAPACITY, fault_scenario=scenario, seed=SEED)
    actions = TRIGGER_SEQUENCES[scenario] if scenario else NO_FAULT_ACTIONS
    for action, value in actions:
        p.step(action, value)
    assert p.verify_seed_replay_determinism(actions) is True


# ----------------------------------------------------------------------
# Reference model must enforce capacity (regression test for the bug
# found and fixed during Spike A validation)
# ----------------------------------------------------------------------

def test_reference_model_enforces_capacity():
    """The reference/expected model must reject pushes past capacity,
    matching correct FIFO behavior — otherwise FIFO_003/FIFO_004 mismatches
    are silently masked. This is a regression test for that exact bug."""
    p = ToyProcess(capacity=CAPACITY, seed=SEED)
    for value in range(1, 7):  # push 6 items into a capacity-4 FIFO
        p.step("push", value)
    assert len(p._reference) <= CAPACITY, (
        "reference model exceeded capacity — it must enforce the same "
        "capacity limit as a correct FIFO to be a valid comparison baseline"
    )


# ----------------------------------------------------------------------
# FIFO_005 canary: confirmed non-monotonic
# ----------------------------------------------------------------------

def test_fifo_005_is_non_monotonic():
    """Confirms FIFO_005's predicate genuinely goes true then false again
    — this is the documented, deliberate exception to the monotonicity
    assumption the bisection engine otherwise relies on."""
    p = ToyProcess(capacity=CAPACITY, fault_scenario=FaultScenario.POINTER_WRAPAROUND, seed=SEED)
    trace = []
    for action, value in TRIGGER_SEQUENCES[FaultScenario.POINTER_WRAPAROUND]:
        p.step(action, value)
        trace.append(p.fault_present())
    assert any(trace), "expected the fault to manifest at least once"
    assert not all(trace[i] <= trace[i + 1] for i in range(len(trace) - 1)), (
        "expected FIFO_005 to be non-monotonic; if this now passes, the "
        "canary scenario may need revisiting"
    )
