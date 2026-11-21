"""
Shared binary-search-over-checkpoints engine for Gacrux.

Given an ordered sequence of checkpoints and a predicate function that
reports whether a fault/condition is present at a given checkpoint, find
the earliest checkpoint where the predicate first becomes true.

Assumes monotonicity: once the predicate is true at checkpoint i, it is
true for all checkpoints j > i. This is the same assumption `git bisect`
makes about a "good...bad" commit range.

MONOTONICITY GUARD: find_earliest_fault_over_steps() records every point
it evaluates during the search and, afterward, checks those points for
internal consistency with the monotonicity assumption (any evaluated
point that's True followed by a later evaluated point that's False is a
direct contradiction). This costs nothing extra — it's bookkeeping on
values already computed — but it only catches violations that happen to
land on points the search actually visited; it cannot prove the absence
of a violation elsewhere in the run. Real hardware faults can behave this
way: an error is detected on one clock cycle, then the signal is
re-evaluated on the next cycle and the status changes or the state
recovers, exactly like the FIFO_005 canary in the fault corpus
(shared/fault_scenarios/CORPUS.md).

For a stronger (but much more expensive) guarantee, pass full_scan=True
to evaluate every single step rather than bisecting — this is the only
way to be certain a transient fault isn't missed, at the cost of losing
all of bisection's performance advantage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

from shared.schema.checkpoint_schema import CheckpointRecord

PredicateFn = Callable[[CheckpointRecord], bool]


def find_earliest_fault(
    checkpoints: Sequence[CheckpointRecord],
    evaluate_predicate: PredicateFn,
) -> CheckpointRecord | None:
    """Binary search for the earliest checkpoint where the predicate holds.

    Args:
        checkpoints: Checkpoints ordered by sequence_index, ascending.
        evaluate_predicate: Callable that restores/inspects state at a
            checkpoint and returns True if the fault condition is present.

    Returns:
        The earliest CheckpointRecord where the predicate is True, or
        None if the predicate is never True across the whole sequence.

    NOTE: this simple per-checkpoint API does not carry the monotonicity
    guard implemented in find_earliest_fault_over_steps() below. Prefer
    that function for anything beyond a quick one-off check.
    """
    if not checkpoints:
        return None

    lo, hi = 0, len(checkpoints) - 1

    # Fast-fail: if the predicate never fires, there's nothing to find.
    if not _eval_cached(checkpoints[hi], evaluate_predicate):
        return None

    result = checkpoints[hi]
    while lo < hi:
        mid = (lo + hi) // 2
        if _eval_cached(checkpoints[mid], evaluate_predicate):
            result = checkpoints[mid]
            hi = mid
        else:
            lo = mid + 1

    return result


@dataclass
class BisectionResult:
    """Result of find_earliest_fault_over_steps(), including monotonicity
    guard information so a caller can tell a trustworthy answer from one
    that should be treated with suspicion.
    """

    earliest_fault_step: int | None
    method: str  # "bisection" or "full_scan"
    monotonicity_violation_detected: bool
    evaluated_points: list[tuple[int, bool]] = field(default_factory=list)

    @property
    def reliable(self) -> bool:
        """False if the monotonicity guard found a contradiction among the
        points actually evaluated. True does NOT prove the run really is
        monotonic — only that no violation was observed among the points
        checked (all of them, if method == "full_scan"; a sparse subset,
        if method == "bisection")."""
        return not self.monotonicity_violation_detected


def find_earliest_fault_over_steps(
    total_steps: int,
    evaluate_step_predicate: Callable[[int], bool],
    full_scan: bool = False,
    guard_samples: int = 8,
) -> BisectionResult:
    """Find the earliest step index where the predicate holds.

    Unlike find_earliest_fault() above, this operates directly on step
    indices rather than a list of saved CheckpointRecords. This is the
    realistic case: checkpoints are sparse (e.g. every N steps), but the
    fault can be pinpointed to an exact step by combining restore-to-
    nearest-checkpoint with deterministic replay forward (see
    spike_a_software/src/checkpointed_run.py's goto_step()). The caller's
    evaluate_step_predicate closure is expected to do that reconstruction
    internally — this function only cares about step indices.

    MONOTONICITY GUARD DESIGN NOTE: a naive version of this guard — just
    recording whatever points plain bisection happens to visit — has a
    real blind spot: the fast-fail path (checking only the final step) can
    visit as few as ONE point, which can never contradict anything, so a
    transient fault gets silently missed AND reported as "reliable" at the
    same time. To close that gap, this function always evaluates
    `guard_samples` evenly-spaced points up front (including step 0 and
    the final step) before deciding whether to fast-fail. This raises the
    odds of catching a violation for a small, constant extra cost — it is
    NOT a guarantee. A violation between two unsampled points is still
    possible. Only full_scan=True guarantees catching it.

    Args:
        total_steps: number of steps in the run (steps are 0..total_steps-1).
        evaluate_step_predicate: given a step index, reconstructs state at
            that step (via restore + replay) and returns whether the fault
            condition is present.
        full_scan: if True, evaluate every step instead of bisecting.
            Guarantees the true earliest fault is found even if the run is
            non-monotonic, at the cost of O(total_steps) evaluations
            instead of O(log total_steps) + guard_samples. Opt-in only —
            expensive.
        guard_samples: number of evenly-spaced points to check up front as
            a monotonicity sanity check before relying on fast-fail.
            Ignored if full_scan=True.

    Returns:
        A BisectionResult. Check `.reliable` (or
        `.monotonicity_violation_detected`) before trusting
        `.earliest_fault_step` at face value. `.reliable == True` means
        no violation was observed among the points evaluated — it does
        NOT prove the run is actually monotonic everywhere.
    """
    if total_steps <= 0:
        return BisectionResult(None, "full_scan" if full_scan else "bisection", False, [])

    evaluated: dict[int, bool] = {}

    def eval_and_record(i: int) -> bool:
        if i in evaluated:
            return evaluated[i]
        v = evaluate_step_predicate(i)
        evaluated[i] = v
        return v

    if full_scan:
        for i in range(total_steps):
            eval_and_record(i)
        earliest = next((i for i in range(total_steps) if evaluated[i]), None)
        points = sorted(evaluated.items())
        return BisectionResult(earliest, "full_scan", _has_monotonicity_violation(points), points)

    # Coarse upfront sampling, so the fast-fail path below isn't relying
    # on a single evaluated point.
    n_samples = min(guard_samples, total_steps)
    if n_samples > 1:
        sample_indices = sorted({
            round(i * (total_steps - 1) / (n_samples - 1)) for i in range(n_samples)
        })
    else:
        sample_indices = [total_steps - 1]
    for i in sample_indices:
        eval_and_record(i)

    lo, hi = 0, total_steps - 1

    if not eval_and_record(hi):
        # Fast-fail candidate — but check whether any sampled point
        # already contradicts this before accepting it.
        if any(v for v in evaluated.values()):
            points = sorted(evaluated.items())
            earliest_known = min(i for i, v in points if v)
            return BisectionResult(earliest_known, "bisection", True, points)
        points = sorted(evaluated.items())
        return BisectionResult(None, "bisection", _has_monotonicity_violation(points), points)

    result = hi
    while lo < hi:
        mid = (lo + hi) // 2
        if eval_and_record(mid):
            result = mid
            hi = mid
        else:
            lo = mid + 1

    points = sorted(evaluated.items())
    return BisectionResult(result, "bisection", _has_monotonicity_violation(points), points)


def _has_monotonicity_violation(points: list[tuple[int, bool]]) -> bool:
    """True if any earlier-evaluated point is True while a later-evaluated
    point is False — a direct contradiction of the monotonicity
    assumption. `points` must be sorted by step ascending. O(k^2) in the
    number of evaluated points, which is small (O(log N) for bisection,
    O(N) for full_scan) so this is cheap in absolute terms either way.
    """
    for i in range(len(points)):
        if not points[i][1]:
            continue
        for j in range(i + 1, len(points)):
            if not points[j][1]:
                return True
    return False


def _eval_cached(record: CheckpointRecord, evaluate_predicate: PredicateFn) -> bool:
    """Evaluate the predicate, using/populating the record's cache."""
    if record.predicate_cache is not None:
        return record.predicate_cache
    result = evaluate_predicate(record)
    record.predicate_cache = result
    return result
