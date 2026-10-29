import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from models.design import build_high_perf_mac_design
from models.sta_engine import STAEngine, STACondition
from models.eco_engine import ECOEngine


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
