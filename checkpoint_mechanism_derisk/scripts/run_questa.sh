#!/usr/bin/env bash
# Runs the checkpoint mechanism de-risk experiment under QuestaSim:
#   1. Reference phase: full uninterrupted run, invoking `checkpoint` at
#      cycle 50 via a .do script (Questa typically checkpoints from the
#      Tcl console/do-file, not from within the SV testbench itself).
#   2. Restore phase: fresh vsim invocation using `restore` to resume
#      from the saved checkpoint, then runs forward to the same end point.
#   3. Diffs the two resulting traces.
#
# TODO: fill in the exact checkpoint/restore Tcl commands per your Questa
# version before relying on this result.

set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results

vlib work
vlog -sv rtl/derisk_counter.sv tb/tb_derisk.sv

echo "=== Reference phase ==="
# TODO: add a `checkpoint questa_ckpt.ckp` call in the .do script at the
# point corresponding to cycle 50 (e.g. via a breakpoint/callback, since
# Questa checkpoints are typically Tcl-console-driven rather than
# testbench-driven).
vsim -c -voptargs=+acc +PHASE=reference -do "run -all; quit" tb_derisk

echo "=== Restore phase ==="
# TODO: replace with the actual restore invocation, e.g.:
#   vsim -c -restore questa_ckpt.ckp -do "run -all; quit"
vsim -c +PHASE=restore -do "run -all; quit" tb_derisk

echo "=== Diff from checkpoint cycle (50) onward ==="
tail -n +50 results/reference_trace.txt > /tmp/ref_tail.txt
tail -n +50 results/restored_trace.txt > /tmp/restored_tail.txt
if diff -q /tmp/ref_tail.txt /tmp/restored_tail.txt > /dev/null; then
    echo "PASS: restored trace matches reference trace from checkpoint onward."
else
    echo "FAIL: divergence detected. See diff below."
    diff /tmp/ref_tail.txt /tmp/restored_tail.txt || true
fi
