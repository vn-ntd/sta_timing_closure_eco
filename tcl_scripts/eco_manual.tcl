###############################################################################
# Engineering Change Order (ECO) Manual Script for Timing Closure
# Target Tools: Synopsys PrimeTime-ECO / Cadence Tempus / OpenROAD OpenSTA
# Design: Crypto_MAC_Unit (1.25 GHz, Tclk = 800 ps)
###############################################################################

puts "=========================================================================="
puts "  STARTING MANUAL ECO TIMING CLOSURE RUN"
puts "=========================================================================="

# -----------------------------------------------------------------------------
# ECO STEP 1: FIX HIGH FANOUT NET (HFN) & SLEW VIOLATIONS
# Net: 'ctrl_enable' has 65 loads (wire_cap=110 fF, total load=210 fF)
# Driver: u_ctrl_drv (BUF_X1_SVT) -> severe slew degradation (> 90 ps)
# Action: Upsize root driver to BUF_X8_SVT and build 2-level buffer tree.
# -----------------------------------------------------------------------------
puts ">> [ECO-1] Resolving High Fanout Net on 'ctrl_enable'..."
size_cell u_ctrl_drv BUF_X8_SVT

# Insert buffer repeater for ALU control branch
insert_buffer -net ctrl_enable -inst u_buf_eco_ctrl_alu -cell BUF_X4_SVT -pin u_alu_stage4_and/B

# Construct buffer tree repeaters to limit max fanout to 16 per net branch
split_fanout -net ctrl_enable -cell BUF_X4_SVT -max_fanout 16


# -----------------------------------------------------------------------------
# ECO STEP 2: CELL RESIZING (UPSIZING) ON SETUP CRITICAL PATH
# Upgrade weak X1 drivers to X2/X4 to drive wire & pin loads with lower resistance
# -----------------------------------------------------------------------------
puts ">> [ECO-2] Upsizing weak drivers along ALU critical pipeline..."
size_cell u_alu_stage1_fa   FA_X2_HVT
size_cell u_alu_stage2_aoi  AOI21_X2_HVT
size_cell u_alu_stage3_xor  XOR2_X2_HVT
size_cell u_alu_stage4_and  AND2_X4_HVT
size_cell u_alu_stage5_mux  MUX2_X2_HVT
size_cell u_alu_stage8_xor  XOR2_X2_HVT
size_cell u_alu_stage9_and  AND2_X4_HVT


# -----------------------------------------------------------------------------
# ECO STEP 3: THRESHOLD VOLTAGE SWAPPING (VT SWAPPING: HVT -> LVT)
# Convert critical timing gates from High-VT to Low-VT to slash gate delay by ~30%
# -----------------------------------------------------------------------------
puts ">> [ECO-3] Performing VT-Swapping (HVT -> LVT) on Critical Setup Cone..."
change_cell_type u_alu_stage1_fa   FA_X2_LVT
change_cell_type u_alu_stage2_aoi  AOI21_X2_LVT
change_cell_type u_alu_stage3_xor  XOR2_X2_LVT
change_cell_type u_alu_stage4_and  AND2_X4_LVT
change_cell_type u_alu_stage5_mux  MUX2_X2_LVT
change_cell_type u_alu_stage6_or   OR2_X1_LVT
change_cell_type u_alu_stage7_nand NAND2_X1_LVT
change_cell_type u_alu_stage8_xor  XOR2_X2_LVT
change_cell_type u_alu_stage9_and  AND2_X4_LVT


# -----------------------------------------------------------------------------
# ECO STEP 4: FIX HOLD VIOLATION ON FAST STATUS PATH
# Path: u_reg_status_launch -> u_reg_status_capture
# Cause: Positive clock skew + fast LVT buffer (Slack_hold < 0)
# Action: Insert dedicated delay buffer cell (DELAY_CELL_X2_HVT) at capture pin.
# -----------------------------------------------------------------------------
puts ">> [ECO-4] Fixing Hold Time Violation by inserting delay element..."
insert_buffer -net net_status_fast_1 -inst u_hold_delay_buf -cell DELAY_CELL_X2_HVT -pin u_reg_status_capture/D


# -----------------------------------------------------------------------------
# ECO STEP 5: LEAKAGE POWER RECOVERY (POWER ECO)
# Downsize and swap non-critical path cells from LVT to HVT to reclaim leakage!
# -----------------------------------------------------------------------------
puts ">> [ECO-5] Reclaiming leakage power on positive slack non-critical paths..."
size_cell u_noncrit_inv1 INV_X1_HVT
size_cell u_noncrit_inv2 INV_X1_HVT

puts "=========================================================================="
puts "  MANUAL ECO SCRIPT APPLICATION COMPLETED"
puts "=========================================================================="
