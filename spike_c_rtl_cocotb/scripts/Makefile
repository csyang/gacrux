# Cocotb Makefile for Gacrux Spike B FIFO testbench.
# TODO(Phase 1.2): add targets for checkpoint capture/restore invocation
# via simulator-native commands (VCS $save/$restart, Questa checkpoint/restore).

TOPLEVEL_LANG = verilog
SIM ?= questa

VERILOG_SOURCES = $(PWD)/../rtl/fifo.sv
TOPLEVEL = fifo
MODULE = test_fifo

include $(shell cocotb-config --makefiles)/Makefile.sim
