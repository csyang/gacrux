// Trivial free-running counter, deliberately unrelated to the Gacrux FIFO.
// Its only job is to have observable, easily-diffable state (count) whose
// evolution depends on a randomized enable, so that RNG-state continuity
// across a checkpoint/restore is directly testable.

module derisk_counter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic         rand_en,   // driven externally from $random in the TB
    output logic [31:0] count
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 32'd0;
        end else if (rand_en) begin
            count <= count + 32'd1;
        end
    end

endmodule
