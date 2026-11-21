"""
Shared fault scenario identifiers for the Gacrux fault injection corpus.

See CORPUS.md in this directory for full descriptions, predicates, and
monotonicity notes for each scenario. This module just gives both Spike A
(Python) and any Python-side orchestration for Spike B/C a single source
of truth for scenario IDs, so they can't drift out of sync by accident.
"""

from enum import Enum


class FaultScenario(str, Enum):
    OFF_BY_ONE_WRITE_PTR = "FIFO_001"
    DROPPED_WRITE_BACK_TO_BACK = "FIFO_002"
    FULL_FLAG_LATE = "FIFO_003"
    EMPTY_FLAG_EARLY = "FIFO_004"
    POINTER_WRAPAROUND = "FIFO_005"  # canary: NOT monotonic, see CORPUS.md


# Scenarios expected to satisfy the standard PoC success criterion
# (bisection converges to the checkpoint interval containing the fault).
# FIFO_005 is deliberately excluded — see CORPUS.md.
MONOTONIC_SCENARIOS = [
    FaultScenario.OFF_BY_ONE_WRITE_PTR,
    FaultScenario.DROPPED_WRITE_BACK_TO_BACK,
    FaultScenario.FULL_FLAG_LATE,
    FaultScenario.EMPTY_FLAG_EARLY,
]

NON_MONOTONIC_CANARY_SCENARIOS = [
    FaultScenario.POINTER_WRAPAROUND,
]
