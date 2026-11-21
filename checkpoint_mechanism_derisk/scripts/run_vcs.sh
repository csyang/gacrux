#!/usr/bin/env bash
# Runs the checkpoint mechanism de-risk experiment under VCS:
#   1. Reference phase: full uninterrupted run, saves a checkpoint at
#      cycle 50 along the way (see TODO in tb_derisk.sv for exact
#      $save syntax — fill in once confirmed for your VCS version).
#   2. Restore phase: fresh sim invocation restarted from the saved
#      checkpoint (see TODO for exact $restart / -r invocation), runs
#      forward to the same end point.
#   3. Diffs the two resulting traces.
#
# TODO: fill in the exact $save/$restart invocation per your VCS version
# before relying on this result.

set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results

vcs -sverilog -full64 \
    -timescale=1ns/1ps \
    rtl/derisk_counter.sv \
    tb/tb_derisk.sv \
    -o simv

echo "=== Reference phase ==="
./simv +PHASE=reference

echo "=== Restore phase ==="
# TODO: replace with the actual restart invocation, e.g.:
#   ./simv -r checkpoint.save +PHASE=restore
./simv +PHASE=restore

echo "=== Diff from checkpoint cycle (50) onward ==="
tail -n +50 results/reference_trace.txt > /tmp/ref_tail.txt
tail -n +50 results/restored_trace.txt > /tmp/restored_tail.txt
if diff -q /tmp/ref_tail.txt /tmp/restored_tail.txt > /dev/null; then
    echo "PASS: restored trace matches reference trace from checkpoint onward."
else
    echo "FAIL: divergence detected. See diff below."
    diff /tmp/ref_tail.txt /tmp/restored_tail.txt || true
fi
