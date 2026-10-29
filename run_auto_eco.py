"""
Demonstration of Automated / Algorithmic ECO Timing Closure.
Iteratively optimizes Setup Slack, inserts Hold Buffers, splits HFNs, and recovers Leakage Power.
"""

from models.design import build_high_perf_mac_design
from models.eco_engine import ECOEngine
from models.sta_engine import STAEngine


def run_auto_eco_demo():
    print("=" * 84)
    print("  RUNNING AUTOMATED / ALGORITHMIC ECO TIMING CLOSURE")
    print("=" * 84)

    design = build_high_perf_mac_design()
    sta_initial = STAEngine(design)
    rep_setup_init = sta_initial.analyze_setup_critical_path()
    rep_hold_init = sta_initial.analyze_hold_critical_path()

    print(f"Initial Setup Slack (WNS): {rep_setup_init.slack:.2f} ps ({'VIOLATED' if rep_setup_init.slack < 0 else 'MET'})")
    print(f"Initial Hold Slack  (WNS): {rep_hold_init.slack:.2f} ps ({'VIOLATED' if rep_hold_init.slack < 0 else 'MET'})")

    eco = ECOEngine(design)
    results = eco.run_automated_timing_closure(max_iterations=12)

    print("\n>>> Auto-ECO Optimization Steps Executed:")
    for step in results["steps"]:
        print(f"  * {step}")

    sta_final = STAEngine(design)
    rep_setup_fin = sta_final.analyze_setup_critical_path()
    rep_hold_fin = sta_final.analyze_hold_critical_path()

    print("\n" + "=" * 84)
    print(f"Final Setup Slack (WNS): {rep_setup_fin.slack:.2f} ps ({'VIOLATED' if rep_setup_fin.slack < 0 else 'MET'})")
    print(f"Final Hold Slack  (WNS): {rep_hold_fin.slack:.2f} ps ({'VIOLATED' if rep_hold_fin.slack < 0 else 'MET'})")
    print("=" * 84)

main = run_auto_eco_demo

if __name__ == "__main__":
    main()
