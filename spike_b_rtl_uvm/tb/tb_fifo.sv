// Traditional SystemVerilog testbench for Gacrux Spike B FIFO DUT.
//
// This is a plain SV testbench (no UVM base classes) so it can be run
// standalone with VCS or QuestaSim. It's structured with a clean
// driver/monitor/scoreboard split so it can be grown into a full UVM
// environment later without a rewrite, per the "may or may not use UVM"
// framing for this spike.
//
// TODO(Phase 1.2): implement checkpoint capture/restore via simulator-
// native mechanisms:
//   - VCS:       $save / $restart system tasks
//   - QuestaSim: checkpoint / restore Tcl commands
// and wire a fault predicate (assertion violation or scoreboard
// mismatch) into the shared bisection engine (shared/bisection/engine.py).

`timescale 1ns/1ps

module tb_fifo;

    localparam int DATA_WIDTH = 8;
    localparam int DEPTH      = 16;

    logic                  clk;
    logic                  rst_n;
    logic                  wr_en;
    logic [DATA_WIDTH-1:0] wr_data;
    logic                  rd_en;
    logic [DATA_WIDTH-1:0] rd_data;
    logic                  full;
    logic                  empty;

    // Reference model queue for scoreboarding.
    logic [DATA_WIDTH-1:0] ref_queue[$];

    fifo #(
        .DATA_WIDTH(DATA_WIDTH),
        .DEPTH(DEPTH)
    ) dut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .wr_data(wr_data),
        .rd_en(rd_en),
        .rd_data(rd_data),
        .full(full),
        .empty(empty)
    );

    // Clock generation
    initial clk = 0;
    always #5 clk = ~clk;

    // Reset task
    task automatic do_reset();
        rst_n   = 0;
        wr_en   = 0;
        rd_en   = 0;
        wr_data = '0;
        ref_queue.delete();
        repeat (2) @(posedge clk);
        rst_n = 1;
        @(posedge clk);
    endtask

    // Driver: push a value
    task automatic push(input logic [DATA_WIDTH-1:0] data);
        @(posedge clk);
        if (!full) begin
            wr_en   = 1;
            wr_data = data;
            ref_queue.push_back(data);
        end
        @(posedge clk);
        wr_en = 0;
    endtask

    // Driver: pop a value, scoreboard-check against reference model
    task automatic pop();
        logic [DATA_WIDTH-1:0] expected;
        @(posedge clk);
        if (!empty) begin
            rd_en = 1;
            expected = ref_queue.pop_front();
        end
        @(posedge clk);
        rd_en = 0;
        if (expected !== rd_data) begin
            // TODO(Phase 1.2): this is the fault-predicate trigger point.
            // A checkpoint taken around here should be identifiable by
            // the bisection engine as "fault present".
            $error("Scoreboard mismatch: expected %0h, got %0h", expected, rd_data);
        end
    endtask

    initial begin
        do_reset();
        push(8'h5A);
        pop();
        $display("Gacrux Spike B (SV/UVM-optional track) basic test complete.");
        $finish;
    end

endmodule
