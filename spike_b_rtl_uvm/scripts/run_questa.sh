#!/usr/bin/env bash
# Run Gacrux Spike B testbench under QuestaSim.
# TODO(Phase 1.2): add checkpoint/restore Tcl hooks once the
# checkpoint-interval strategy is decided (see docs/PHASES.md).

set -euo pipefail
cd "$(dirname "$0")/.."

vlib work
vlog -sv rtl/fifo.sv tb/tb_fifo.sv
vsim -c -do "run -all; quit" tb_fifo
