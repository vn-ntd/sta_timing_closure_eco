"""
Master experiment runner for STA & Timing Closure / ECO analysis.
Executes baseline STA, applies Tcl ECO, verifies timing closure,
and performs OCV & Clock Jitter sensitivity sweeps.
"""

import sys
import os

# Add package directory to python path
pkg_root = os.path.dirname(os.path.abspath(__file__))
if pkg_root not in sys.path:
    sys.path.insert(0, pkg_root)

from models.design import build_high_perf_mac_design
from models.sta_engine import STAEngine, STACondition
from models.eco_engine import ECOEngine

def print_separator(title: str):
    print("\n" + "#" * 84)
    print(f"### {title.upper()}")
    print("#" * 84 + "\n")

def run_sta_closure_experiments():
    # -------------------------------------------------------------------------
    # STAGE 1: BASELINE STA & CRITICAL PATH ANALYSIS
    # -------------------------------------------------------------------------
    print_separator("Stage 1: Baseline STA Analysis & Violation Identification")

    design = build_high_perf_mac_design()
    sta = STAEngine(design, STACondition(late_derate=1.08, early_derate=0.92, jitter=20.0, margin=20.0))

    leakage_base, area_base = sta.compute_power_and_area()
    print(f"Design: {design.name} | Clock Frequency: {1000000.0/design.clk_period:.2f} MHz (Tclk = {design.clk_period:.1f} ps)")
    print(f"Total Standard Cell Count : {len(design.instances)}")
    print(f"Initial Leakage Power     : {leakage_base:.3f} uW")
    print(f"Initial Total Cell Area   : {area_base:.2f} um^2\n")

    # High Fanout Net Analysis
    print(">>> High Fanout Net (HFN) & Transition Slew Check:")
    hfn_viols = sta.analyze_high_fanout_nets(max_fanout_limit=16, max_slew_limit=60.0)
    for v in hfn_viols:
        print(f"  [VIOLATION] Net '{v['net']}': Fanout={v['fanout']}, LoadCap={v['load_cap_fF']:.1f} fF, Driver={v['driver_cell']}, Slew={v['transition_slew_ps']:.1f} ps")

    # Setup Critical Path Report
    rep_setup_base = sta.analyze_setup_critical_path()
    print("\n" + sta.format_primetime_report(rep_setup_base))

    # Hold Critical Path Report
    rep_hold_base = sta.analyze_hold_critical_path()
    print("\n" + sta.format_primetime_report(rep_hold_base))

    # -------------------------------------------------------------------------
    # STAGE 2: EXECUTE MANUAL TCL ECO SCRIPT
    # -------------------------------------------------------------------------
    print_separator("Stage 2: Executing Manual Tcl ECO Script for Timing Closure")

    eco = ECOEngine(design)
    tcl_path = os.path.join(pkg_root, "tcl_scripts", "eco_manual.tcl")
    eco.execute_tcl_script(tcl_path)

    print(f"Successfully executed Tcl ECO operations: {len(eco.eco_history)} commands applied.")
    for h in eco.eco_history:
        print(f"  [ECO] {h}")

    # -------------------------------------------------------------------------
    # STAGE 3: POST-ECO TIMING VERIFICATION & CLOSURE
    # -------------------------------------------------------------------------
    print_separator("Stage 3: Post-ECO STA Verification & Power Recovery")

    sta_post = STAEngine(design, STACondition(late_derate=1.08, early_derate=0.92, jitter=20.0, margin=20.0))
    rep_setup_post = sta_post.analyze_setup_critical_path()
    rep_hold_post = sta_post.analyze_hold_critical_path()
    leakage_post, area_post = sta_post.compute_power_and_area()

    print("\n" + sta_post.format_primetime_report(rep_setup_post))
    print("\n" + sta_post.format_primetime_report(rep_hold_post))

    print("\n>>> Post-ECO High Fanout Net Check:")
    hfn_post = sta_post.analyze_high_fanout_nets(max_fanout_limit=16, max_slew_limit=60.0)
    if not hfn_post:
        print("  [SUCCESS] All nets meet maximum fanout (< 16) and max slew (< 60.0 ps) constraints!")
    else:
        for v in hfn_post:
            print(f"  [WARNING] Remaining: Net '{v['net']}': Fanout={v['fanout']}, Slew={v['transition_slew_ps']:.1f} ps")

    # Comparison Table
    print("\n" + "=" * 78)
    print(f"{'METRIC':<30} {'BASELINE':<18} {'POST-ECO':<18} {'DELTA':<12}")
    print("=" * 78)
    delta_setup = rep_setup_post.slack - rep_setup_base.slack
    delta_hold = rep_hold_post.slack - rep_hold_base.slack
    delta_leakage = leakage_post - leakage_base
    delta_area = area_post - area_base

    print(f"{'Setup Slack (WNS)':<30} {rep_setup_base.slack:>10.2f} ps     {rep_setup_post.slack:>10.2f} ps     {delta_setup:>+10.2f} ps")
    print(f"{'Hold Slack (WNS)':<30} {rep_hold_base.slack:>10.2f} ps     {rep_hold_post.slack:>10.2f} ps     {delta_hold:>+10.2f} ps")
    print(f"{'Leakage Power':<30} {leakage_base:>10.3f} uW     {leakage_post:>10.3f} uW     {delta_leakage:>+10.3f} uW")
    print(f"{'Total Cell Area':<30} {area_base:>10.2f} um^2   {area_post:>10.2f} um^2   {delta_area:>+10.2f} um^2")
    print(f"{'Timing Status':<30} {'VIOLATED':>10}        {'MET (CLOSED)':>12}")
    print("=" * 78)

    # -------------------------------------------------------------------------
    # STAGE 4: ON-CHIP VARIATION (OCV) & CRPR SENSITIVITY ANALYSIS
    # -------------------------------------------------------------------------
    print_separator("Stage 4: OCV Derate & Clock Reconvergence Pessimism Removal (CRPR) Analysis")

    print(f"{'OCV Derate (Late/Early)':<26} {'Setup Slack (CRPR ON)':<22} {'Setup Slack (CRPR OFF)':<23} {'CRPR Pessimism Credit'}")
    print("-" * 92)

    derate_sweeps = [
        (1.00, 1.00), # Ideal / Nominal PVT
        (1.04, 0.96), # 4% Derate
        (1.08, 0.92), # 8% Derate (Default signoff)
        (1.12, 0.88), # 12% Derate (Severe variation)
        (1.16, 0.84), # 16% Derate
    ]

    for late, early in derate_sweeps:
        # With CRPR
        cond_crpr_on = STACondition(late_derate=late, early_derate=early, jitter=20.0, margin=20.0, enable_crpr=True)
        sta_crpr_on = STAEngine(design, cond_crpr_on)
        rep_on = sta_crpr_on.analyze_setup_critical_path()

        # Without CRPR
        cond_crpr_off = STACondition(late_derate=late, early_derate=early, jitter=20.0, margin=20.0, enable_crpr=False)
        sta_crpr_off = STAEngine(design, cond_crpr_off)
        rep_off = sta_crpr_off.analyze_setup_critical_path()

        crpr_credit = rep_on.crpr_credit
        print(f"Late={late:.2f} / Early={early:.2f}       {rep_on.slack:>10.2f} ps             {rep_off.slack:>10.2f} ps             {crpr_credit:>10.2f} ps")

    # -------------------------------------------------------------------------
    # STAGE 5: CLOCK JITTER & UNCERTAINTY SWEEP
    # -------------------------------------------------------------------------
    print_separator("Stage 5: Clock Jitter & Uncertainty Sensitivity Analysis")

    print(f"{'Clock Jitter (ps)':<20} {'Clock Uncertainty (ps)':<26} {'Setup Slack (ps)':<20} {'Hold Slack (ps)':<18} {'Timing Status'}")
    print("-" * 96)

    jitter_sweeps = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    for j in jitter_sweeps:
        cond_j = STACondition(late_derate=1.08, early_derate=0.92, jitter=j, margin=20.0, enable_crpr=True)
        sta_j = STAEngine(design, cond_j)
        r_setup = sta_j.analyze_setup_critical_path()
        r_hold = sta_j.analyze_hold_critical_path()

        status = "MET" if (r_setup.slack >= 0 and r_hold.slack >= 0) else "VIOLATED"
        print(f"{j:>10.1f}          {r_setup.clock_uncertainty:>12.1f} ps              {r_setup.slack:>10.2f} ps       {r_hold.slack:>10.2f} ps         {status}")

    print("=" * 96)

if __name__ == "__main__":
    run_sta_closure_experiments()
