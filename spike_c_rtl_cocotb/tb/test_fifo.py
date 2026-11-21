"""
Cocotb testbench for the Gacrux Spike B FIFO DUT.

TODO(Phase 1.2): implement checkpoint capture/restore via simulator-native
mechanisms ($save/$restart for VCS, checkpoint/restore Tcl for QuestaSim),
and wire a fault predicate (assertion violation or scoreboard mismatch)
into the shared bisection engine.
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge


@cocotb.test()
async def test_basic_push_pop(dut):
    """Sanity check: push then pop a single value, confirm round-trip."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    dut.rst_n.value = 0
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wr_data.value = 0
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)

    dut.wr_en.value = 1
    dut.wr_data.value = 0x5A
    await RisingEdge(dut.clk)
    dut.wr_en.value = 0

    dut.rd_en.value = 1
    await RisingEdge(dut.clk)
    dut.rd_en.value = 0
    await RisingEdge(dut.clk)

    assert dut.rd_data.value == 0x5A, "FIFO did not return pushed value"


# TODO(Phase 1.2): add a checkpoint/restore round-trip test once simulator
# checkpoint hooks are implemented in scripts/.
