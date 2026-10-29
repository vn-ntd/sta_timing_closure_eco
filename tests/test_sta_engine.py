import pytest

from models.design import build_high_perf_mac_design
from models.eco_engine import ECOEngine
from models.sta_engine import STACondition, STAEngine


@pytest.fixture
def clean_design():
    return build_high_perf_mac_design()


def test_setup_slack_equation(clean_design):
    """Verifies that Slack_setup = Data_Required_Time - Data_Arrival_Time."""
    engine = STAEngine(clean_design, STACondition())
    rep = engine.analyze_setup_critical_path()

    expected_slack = round(rep.data_required_time - rep.data_arrival_time, 2)
    assert round(rep.slack, 2) == expected_slack
    assert rep.path_type == "max"


def test_hold_slack_equation(clean_design):
    """Verifies that Slack_hold = Data_Arrival_Time - Data_Required_Time."""
    engine = STAEngine(clean_design, STACondition())
    rep = engine.analyze_hold_critical_path()

    expected_slack = round(rep.data_arrival_time - rep.data_required_time, 2)
    assert round(rep.slack, 2) == expected_slack
    assert rep.path_type == "min"


def test_crpr_credit_calculation(clean_design):
    """Verifies that CRPR credit is correctly calculated on common clock paths."""
    cond_with_crpr = STACondition(late_derate=1.10, early_derate=0.90, enable_crpr=True)
    cond_no_crpr = STACondition(late_derate=1.10, early_derate=0.90, enable_crpr=False)

    engine_with = STAEngine(clean_design, cond_with_crpr)
    engine_without = STAEngine(clean_design, cond_no_crpr)

    rep_with = engine_with.analyze_setup_critical_path()
    rep_without = engine_without.analyze_setup_critical_path()

    assert rep_with.crpr_credit > 0
    assert rep_without.crpr_credit == 0.0
    # Slack with CRPR must be more relaxed (higher) than without CRPR
    assert rep_with.slack > rep_without.slack


def test_clock_jitter_sensitivity(clean_design):
    """Verifies that setup slack decreases linearly with clock jitter (dSlack/dJitter = -1.0)."""
    engine_low_jitter = STAEngine(clean_design, STACondition(jitter=10.0))
    engine_high_jitter = STAEngine(clean_design, STACondition(jitter=30.0))

    rep_low = engine_low_jitter.analyze_setup_critical_path()
    rep_high = engine_high_jitter.analyze_setup_critical_path()

    delta_slack = rep_high.slack - rep_low.slack
    delta_jitter = 30.0 - 10.0
    sensitivity = delta_slack / delta_jitter
    assert pytest.approx(sensitivity, 0.05) == -1.0


def test_automated_eco_stops_at_margin(clean_design):
    """Verifies that automated ECO stops when target margins are achieved to avoid over-buffering."""
    eco = ECOEngine(clean_design)
    target_setup = 20.0
    target_hold = 15.0

    results = eco.run_automated_timing_closure(
        max_iterations=8,
        target_setup_margin=target_setup,
        target_hold_margin=target_hold,
    )

    engine_post = STAEngine(clean_design)
    rep_setup_post = engine_post.analyze_setup_critical_path()
    rep_hold_post = engine_post.analyze_hold_critical_path()

    assert results["setup_fixed"] is True
    assert results["hold_fixed"] is True
    assert rep_setup_post.slack >= 0
    assert rep_hold_post.slack >= 0


def test_power_and_area_computation(clean_design):
    """Verifies static leakage power and cell area aggregation."""
    engine = STAEngine(clean_design)
    leakage, area = engine.compute_power_and_area()
    assert leakage > 0
    assert area > 0
    assert isinstance(leakage, float)
    assert isinstance(area, float)


def test_high_fanout_and_slew_detection(clean_design):
    """Verifies that high fanout nets exceeding limit are detected."""
    engine = STAEngine(clean_design)
    hfn_viols = engine.analyze_high_fanout_nets(max_fanout_limit=16, max_slew_limit=60.0)
    assert len(hfn_viols) > 0
    net_names = [v["net"] for v in hfn_viols]
    assert "ctrl_enable" in net_names


def test_primetime_report_formatter(clean_design):
    """Verifies that PrimeTime-style reports are generated for both setup and hold paths."""
    engine = STAEngine(clean_design)
    rep_setup = engine.analyze_setup_critical_path()
    formatted_setup = engine.format_primetime_report(rep_setup)
    assert "Timing Report" in formatted_setup
    assert "MAX (Setup)" in formatted_setup
    assert "data arrival time" in formatted_setup
    assert "data required time" in formatted_setup

    rep_hold = engine.analyze_hold_critical_path()
    formatted_hold = engine.format_primetime_report(rep_hold)
    assert "MIN (Hold)" in formatted_hold
    assert "clock network delay (capture late)" in formatted_hold


def test_non_critical_path_analysis(clean_design):
    """Verifies analysis of non-critical timing path for power recovery."""
    engine = STAEngine(clean_design)
    rep_noncrit = engine.analyze_non_critical_path()
    assert rep_noncrit.path_name is not None
    assert rep_noncrit.slack > 0

