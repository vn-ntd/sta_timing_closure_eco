"""
Master experiment runner for STA & Timing Closure / ECO analysis.
Executes baseline STA, applies Tcl ECO, verifies timing closure,
and performs OCV & Clock Jitter sensitivity sweeps.
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Optional

from models.design import build_high_perf_mac_design
from models.eco_engine import ECOEngine
from models.sta_engine import STACondition, STAEngine

PKG_ROOT = Path(__file__).resolve().parent


def print_separator(title: str):
    print("\n" + "#" * 84)
    print(f"### {title.upper()}")
    print("#" * 84 + "\n")


def run_sta_closure_experiments(
    tcl_script: Optional[str] = None,
    derate_late: float = 1.08,
    derate_early: float = 0.92,
    jitter: float = 20.0,
    margin: float = 20.0,
    export_json: Optional[str] = None,
    export_csv_prefix: Optional[str] = None,
    quiet: bool = False,
) -> dict:
    """
    Executes the 5-stage STA & ECO analysis pipeline.
    Returns structured results dictionary.
    """
    if tcl_script is None:
        tcl_script = str(PKG_ROOT / "tcl_scripts" / "eco_manual.tcl")

    # -------------------------------------------------------------------------
    # STAGE 1: BASELINE STA & CRITICAL PATH ANALYSIS
    # -------------------------------------------------------------------------
    if not quiet:
        print_separator("Stage 1: Baseline STA Analysis & Violation Identification")

    design = build_high_perf_mac_design()
    sta = STAEngine(design, STACondition(late_derate=derate_late, early_derate=derate_early, jitter=jitter, margin=margin))

    leakage_base, area_base = sta.compute_power_and_area()
    if not quiet:
        print(f"Design: {design.name} | Clock Frequency: {1000000.0/design.clk_period:.2f} MHz (Tclk = {design.clk_period:.1f} ps)")
        print(f"Total Standard Cell Count : {len(design.instances)}")
        print(f"Initial Leakage Power     : {leakage_base:.3f} uW")
        print(f"Initial Total Cell Area   : {area_base:.2f} um^2\n")

        # High Fanout Net Analysis
        print(">>> High Fanout Net (HFN) & Transition Slew Check:")
    hfn_viols = sta.analyze_high_fanout_nets(max_fanout_limit=16, max_slew_limit=60.0)
    if not quiet:
        for v in hfn_viols:
            print(f"  [VIOLATION] Net '{v['net']}': Fanout={v['fanout']}, LoadCap={v['load_cap_fF']:.1f} fF, Driver={v['driver_cell']}, Slew={v['transition_slew_ps']:.1f} ps")

    # Setup Critical Path Report
    rep_setup_base = sta.analyze_setup_critical_path()
    if not quiet:
        print("\n" + sta.format_primetime_report(rep_setup_base))

    # Hold Critical Path Report
    rep_hold_base = sta.analyze_hold_critical_path()
    if not quiet:
        print("\n" + sta.format_primetime_report(rep_hold_base))

    # -------------------------------------------------------------------------
    # STAGE 2: EXECUTE MANUAL TCL ECO SCRIPT
    # -------------------------------------------------------------------------
    if not quiet:
        print_separator("Stage 2: Executing Manual Tcl ECO Script for Timing Closure")

    eco = ECOEngine(design)
    eco.execute_tcl_script(tcl_script)

    if not quiet:
        print(f"Successfully executed Tcl ECO operations: {len(eco.eco_history)} commands applied.")
        for h in eco.eco_history:
            print(f"  [ECO] {h}")

    # -------------------------------------------------------------------------
    # STAGE 3: POST-ECO TIMING VERIFICATION & CLOSURE
    # -------------------------------------------------------------------------
    if not quiet:
        print_separator("Stage 3: Post-ECO STA Verification & Power Recovery")

    sta_post = STAEngine(design, STACondition(late_derate=derate_late, early_derate=derate_early, jitter=jitter, margin=margin))
    rep_setup_post = sta_post.analyze_setup_critical_path()
    rep_hold_post = sta_post.analyze_hold_critical_path()
    leakage_post, area_post = sta_post.compute_power_and_area()

    if not quiet:
        print("\n" + sta_post.format_primetime_report(rep_setup_post))
        print("\n" + sta_post.format_primetime_report(rep_hold_post))
        print("\n>>> Post-ECO High Fanout Net Check:")

    hfn_post = sta_post.analyze_high_fanout_nets(max_fanout_limit=16, max_slew_limit=60.0)
    if not quiet:
        if not hfn_post:
            print("  [SUCCESS] All nets meet maximum fanout (< 16) and max slew (< 60.0 ps) constraints!")
        else:
            for v in hfn_post:
                print(f"  [WARNING] Remaining: Net '{v['net']}': Fanout={v['fanout']}, Slew={v['transition_slew_ps']:.1f} ps")

    # Comparison Table
    delta_setup = rep_setup_post.slack - rep_setup_base.slack
    delta_hold = rep_hold_post.slack - rep_hold_base.slack
    delta_leakage = leakage_post - leakage_base
    delta_area = area_post - area_base

    print("\n" + "=" * 78)
    print(f"{'METRIC':<30} {'BASELINE':<18} {'POST-ECO':<18} {'DELTA':<12}")
    print("=" * 78)
    print(f"{'Setup Slack (WNS)':<30} {rep_setup_base.slack:>10.2f} ps     {rep_setup_post.slack:>10.2f} ps     {delta_setup:>+10.2f} ps")
    print(f"{'Hold Slack (WNS)':<30} {rep_hold_base.slack:>10.2f} ps     {rep_hold_post.slack:>10.2f} ps     {delta_hold:>+10.2f} ps")
    print(f"{'Leakage Power':<30} {leakage_base:>10.3f} uW     {leakage_post:>10.3f} uW     {delta_leakage:>+10.3f} uW")
    print(f"{'Total Cell Area':<30} {area_base:>10.2f} um^2   {area_post:>10.2f} um^2   {delta_area:>+10.2f} um^2")
    status_base = "MET" if (rep_setup_base.slack >= 0 and rep_hold_base.slack >= 0) else "VIOLATED"
    status_post = "MET (CLOSED)" if (rep_setup_post.slack >= 0 and rep_hold_post.slack >= 0) else "VIOLATED"
    print(f"{'Timing Status':<30} {status_base:>10}        {status_post:>12}")
    print("=" * 78)

    # -------------------------------------------------------------------------
    # STAGE 4: ON-CHIP VARIATION (OCV) & CRPR SENSITIVITY ANALYSIS
    # -------------------------------------------------------------------------
    if not quiet:
        print_separator("Stage 4: OCV Derate & Clock Reconvergence Pessimism Removal (CRPR) Analysis")
        print(f"{'OCV Derate (Late/Early)':<26} {'Setup Slack (CRPR ON)':<22} {'Setup Slack (CRPR OFF)':<23} {'CRPR Pessimism Credit'}")
        print("-" * 92)

    derate_sweeps = [
        (1.00, 1.00),  # Ideal / Nominal PVT
        (1.04, 0.96),  # 4% Derate
        (1.08, 0.92),  # 8% Derate (Default signoff)
        (1.12, 0.88),  # 12% Derate (Severe variation)
        (1.16, 0.84),  # 16% Derate
    ]

    ocv_sweep_data = []
    for late, early in derate_sweeps:
        cond_crpr_on = STACondition(late_derate=late, early_derate=early, jitter=jitter, margin=margin, enable_crpr=True)
        sta_crpr_on = STAEngine(design, cond_crpr_on)
        rep_on = sta_crpr_on.analyze_setup_critical_path()

        cond_crpr_off = STACondition(late_derate=late, early_derate=early, jitter=jitter, margin=margin, enable_crpr=False)
        sta_crpr_off = STAEngine(design, cond_crpr_off)
        rep_off = sta_crpr_off.analyze_setup_critical_path()

        crpr_credit = rep_on.crpr_credit
        ocv_sweep_data.append({
            "late_derate": late,
            "early_derate": early,
            "setup_slack_crpr_on_ps": round(rep_on.slack, 2),
            "setup_slack_crpr_off_ps": round(rep_off.slack, 2),
            "crpr_credit_ps": round(crpr_credit, 2),
        })
        if not quiet:
            print(f"Late={late:.2f} / Early={early:.2f}       {rep_on.slack:>10.2f} ps             {rep_off.slack:>10.2f} ps             {crpr_credit:>10.2f} ps")

    # -------------------------------------------------------------------------
    # STAGE 5: CLOCK JITTER & UNCERTAINTY SWEEP
    # -------------------------------------------------------------------------
    if not quiet:
        print_separator("Stage 5: Clock Jitter & Uncertainty Sensitivity Analysis")
        print(f"{'Clock Jitter (ps)':<20} {'Clock Uncertainty (ps)':<26} {'Setup Slack (ps)':<20} {'Hold Slack (ps)':<18} {'Timing Status'}")
        print("-" * 96)

    jitter_sweeps = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    jitter_sweep_data = []
    for j in jitter_sweeps:
        cond_j = STACondition(late_derate=derate_late, early_derate=derate_early, jitter=j, margin=margin, enable_crpr=True)
        sta_j = STAEngine(design, cond_j)
        r_setup = sta_j.analyze_setup_critical_path()
        r_hold = sta_j.analyze_hold_critical_path()

        status = "MET" if (r_setup.slack >= 0 and r_hold.slack >= 0) else "VIOLATED"
        jitter_sweep_data.append({
            "jitter_ps": j,
            "clock_uncertainty_ps": round(r_setup.clock_uncertainty, 1),
            "setup_slack_ps": round(r_setup.slack, 2),
            "hold_slack_ps": round(r_hold.slack, 2),
            "status": status,
        })
        if not quiet:
            print(f"{j:>10.1f}          {r_setup.clock_uncertainty:>12.1f} ps              {r_setup.slack:>10.2f} ps       {r_hold.slack:>10.2f} ps         {status}")

    if not quiet:
        print("=" * 96)

    # Structured summary payload
    summary = {
        "design": design.name,
        "clock_period_ps": design.clk_period,
        "frequency_mhz": round(1_000_000.0 / design.clk_period, 2),
        "total_cells": len(design.instances),
        "operating_condition": {
            "late_derate": derate_late,
            "early_derate": derate_early,
            "jitter_ps": jitter,
            "margin_ps": margin,
        },
        "baseline": {
            "setup_slack_ps": round(rep_setup_base.slack, 2),
            "hold_slack_ps": round(rep_hold_base.slack, 2),
            "leakage_uW": round(leakage_base, 3),
            "area_um2": round(area_base, 2),
            "status": status_base,
        },
        "post_eco": {
            "setup_slack_ps": round(rep_setup_post.slack, 2),
            "hold_slack_ps": round(rep_hold_post.slack, 2),
            "leakage_uW": round(leakage_post, 3),
            "area_um2": round(area_post, 2),
            "status": status_post,
        },
        "delta": {
            "setup_slack_ps": round(delta_setup, 2),
            "hold_slack_ps": round(delta_hold, 2),
            "leakage_uW": round(delta_leakage, 3),
            "area_um2": round(delta_area, 2),
        },
        "ocv_sweep": ocv_sweep_data,
        "jitter_sweep": jitter_sweep_data,
    }

    # Optional JSON export
    if export_json:
        json_path = Path(export_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        print(f"\n[INFO] Successfully exported JSON report to: {json_path}")

    # Optional CSV export
    if export_csv_prefix:
        csv_prefix = Path(export_csv_prefix)
        csv_prefix.parent.mkdir(parents=True, exist_ok=True)

        ocv_csv_path = csv_prefix.parent / f"{csv_prefix.name}_ocv.csv"
        with open(ocv_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(ocv_sweep_data[0].keys()))
            writer.writeheader()
            writer.writerows(ocv_sweep_data)
        print(f"[INFO] Exported OCV sweep CSV to: {ocv_csv_path}")

        jitter_csv_path = csv_prefix.parent / f"{csv_prefix.name}_jitter.csv"
        with open(jitter_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(jitter_sweep_data[0].keys()))
            writer.writeheader()
            writer.writerows(jitter_sweep_data)
        print(f"[INFO] Exported Jitter sweep CSV to: {jitter_csv_path}")

    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="STA & Timing Closure / ECO Experiment Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tcl-script",
        type=str,
        default=str(PKG_ROOT / "tcl_scripts" / "eco_manual.tcl"),
        help="Path to the Tcl ECO script to execute.",
    )
    parser.add_argument(
        "--derate-late",
        type=float,
        default=1.08,
        help="Late OCV derate factor (setup launch / hold capture).",
    )
    parser.add_argument(
        "--derate-early",
        type=float,
        default=0.92,
        help="Early OCV derate factor (setup capture / hold launch).",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=20.0,
        help="Clock jitter uncertainty in picoseconds.",
    )
    parser.add_argument(
        "--margin",
        type=float,
        default=20.0,
        help="Additional signoff timing margin in picoseconds.",
    )
    parser.add_argument(
        "--export-json",
        type=str,
        default=None,
        help="Optional path to output signoff metrics and sweeps in JSON format.",
    )
    parser.add_argument(
        "--export-csv",
        type=str,
        default=None,
        help="Optional prefix path to export OCV and Jitter sweeps to CSV files.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed point-to-point delay path printouts.",
    )

    args = parser.parse_args(argv)
    run_sta_closure_experiments(
        tcl_script=args.tcl_script,
        derate_late=args.derate_late,
        derate_early=args.derate_early,
        jitter=args.jitter,
        margin=args.margin,
        export_json=args.export_json,
        export_csv_prefix=args.export_csv,
        quiet=args.quiet,
    )


if __name__ == "__main__":
    main()
