#!/usr/bin/env bash
# Run Gacrux Spike B testbench under VCS.
# TODO(Phase 1.2): add $save/$restart checkpoint hooks once the
# checkpoint-interval strategy is decided (see docs/PHASES.md).

set -euo pipefail
cd "$(dirname "$0")/.."

vcs -sverilog -full64 \
    -timescale=1ns/1ps \
    rtl/fifo.sv \
    tb/tb_fifo.sv \
    -o simv \
    +define+GACRUX_SPIKE_B

./simv
