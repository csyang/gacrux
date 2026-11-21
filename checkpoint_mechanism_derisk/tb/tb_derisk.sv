// De-risk testbench: exercises the counter DUT with a randomized enable
// signal, and drives the simulator's native checkpoint/restore mechanism
// at a fixed point, to answer whether restore reproduces identical
// downstream behavior (including RNG continuity).
//
// Run in two phases (see scripts/run_vcs.sh and scripts/run_questa.sh):
//
//   Phase "reference": run 0 -> N+100 cycles uninterrupted, save a
//     checkpoint at cycle N along the way, write count/rand_en to
//     results/reference_trace.txt for the full run.
//
//   Phase "restore": start a fresh sim invocation, restore the checkpoint
//     saved at cycle N, then run forward to N+100, writing to
//     results/restored_trace.txt. This should match reference_trace.txt
//     from cycle N onward if RNG state was faithfully restored.
//
// NOTE: exact $save/$restart syntax (VCS) and checkpoint/restore Tcl
// syntax (Questa) vary by tool version. TODOs mark where site-specific
// syntax needs to be confirmed/filled in.

`timescale 1ns/1ps

module tb_derisk;

    localparam int CHECKPOINT_CYCLE = 50;
    localparam int TOTAL_CYCLES     = 150;

    logic        clk;
    logic        rst_n;
    logic        rand_en;
    logic [31:0] count;

    int          cycle_num;
    int          trace_fd;
    string       trace_filename;
    string       phase; // "reference" or "restore", set via plusarg

    derisk_counter dut (
        .clk(clk),
        .rst_n(rst_n),
        .rand_en(rand_en),
        .count(count)
    );

    initial clk = 0;
    always #5 clk = ~clk;

    initial begin
        if (!$value$plusargs("PHASE=%s", phase)) begin
            phase = "reference";
        end

        if (phase == "reference") begin
            trace_filename = "results/reference_trace.txt";
        end else begin
            trace_filename = "results/restored_trace.txt";
        end

        trace_fd = $fopen(trace_filename, "w");

        rst_n   = 0;
        rand_en = 0;
        cycle_num = 0;
        repeat (2) @(posedge clk);
        rst_n = 1;

        if (phase == "restore") begin
            // TODO(VCS): confirm exact restart invocation. Typically the
            // saved state is loaded via a command-line switch to simv
            // (e.g. `simv -r checkpoint.save`) rather than an in-TB call,
            // in which case this branch may not need to do anything
            // beyond skipping re-initialization. Adjust once confirmed.
            //
            // TODO(Questa): confirm exact restore invocation — typically
            // `vsim -restore checkpoint.questa` from the run script rather
            // than an in-TB call. Adjust once confirmed.
            $display("[derisk] Restore phase: assuming simulator was invoked with a restore switch.");
        end

        forever begin
            @(posedge clk);
            rand_en = $random % 2; // RNG-dependent stimulus
            cycle_num++;

            $fdisplay(trace_fd, "%0d %0d %0d", cycle_num, rand_en, count);

            if (phase == "reference" && cycle_num == CHECKPOINT_CYCLE) begin
                // TODO(VCS): $save("checkpoint.save") — confirm exact
                // system task name/arguments for the VCS version in use.
                // TODO(Questa): use `checkpoint` Tcl command via a .do
                // script invoked at this point, or via $stop + manual
                // checkpoint command from the run script — Questa
                // typically checkpoints from the Tcl console/do-file
                // rather than from within the SV testbench itself.
                $display("[derisk] Checkpoint point reached at cycle %0d — invoke simulator checkpoint here.", cycle_num);
            end

            if (cycle_num >= TOTAL_CYCLES) begin
                $fclose(trace_fd);
                $display("[derisk] %s phase complete: %0d cycles, final count=%0d", phase, cycle_num, count);
                $finish;
            end
        end
    end

endmodule
