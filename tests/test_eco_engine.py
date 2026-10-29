import pytest

from models.design import build_high_perf_mac_design
from models.eco_engine import ECOEngine


@pytest.fixture
def sample_design():
    return build_high_perf_mac_design()


def test_size_cell_valid_and_invalid(sample_design):
    eco = ECOEngine(sample_design)

    # Valid sizing
    res = eco.size_cell("u_alu_stage1_fa", "FA_X4_LVT")
    assert res is True
    assert sample_design.instances["u_alu_stage1_fa"].cell_type_name == "FA_X4_LVT"
    assert "size_cell u_alu_stage1_fa" in eco.eco_history[-1]

    # Invalid instance
    with pytest.raises(KeyError, match="not found for sizing"):
        eco.size_cell("u_nonexistent_inst", "BUF_X4_SVT")


def test_change_cell_type_alias(sample_design):
    eco = ECOEngine(sample_design)
    res = eco.change_cell_type("u_alu_stage2_aoi", "AOI21_X2_LVT")
    assert res is True
    assert sample_design.instances["u_alu_stage2_aoi"].cell_type_name == "AOI21_X2_LVT"


def test_insert_buffer_global_and_pin_specific(sample_design):
    eco = ECOEngine(sample_design)

    # 1. Global buffer insertion (no pin specified -> all sinks redirected)
    res_global = eco.insert_buffer(
        net_name="net_mac_stage0",
        inst_name="u_eco_buf_global",
        cell_type="BUF_X4_SVT",
    )
    assert res_global is True
    assert "u_eco_buf_global" in sample_design.instances
    assert "insert_buffer u_eco_buf_global" in eco.eco_history[-1]

    # 2. Pin-specific buffer insertion
    res_pin = eco.insert_buffer(
        net_name="net_status_fast_1",
        inst_name="u_eco_buf_pin",
        cell_type="DELAY_CELL_X2_HVT",
        pin="u_reg_status_capture/D",
    )
    assert res_pin is True
    assert "u_eco_buf_pin" in sample_design.instances
    assert "for pin u_reg_status_capture/D" in eco.eco_history[-1]

    # 3. KeyError on nonexistent net
    with pytest.raises(KeyError, match="Net 'net_nonexistent' not found"):
        eco.insert_buffer("net_nonexistent", "u_buf_dummy", "BUF_X1_SVT")


def test_split_fanout(sample_design):
    eco = ECOEngine(sample_design)
    net_name = "ctrl_enable"
    orig_sink_count = len(sample_design.nets[net_name].sink_pins)
    assert orig_sink_count > 16

    num_clusters = eco.split_fanout(net_name, cell_type="BUF_X4_SVT", max_fanout=16)
    assert num_clusters > 1
    assert "split_fanout ctrl_enable" in eco.eco_history[-1]

    # Verify repeaters added
    for i in range(num_clusters):
        assert f"u_buf_tree_{i}" in sample_design.instances

    # KeyError on nonexistent net
    with pytest.raises(KeyError, match="Net 'net_missing' not found"):
        eco.split_fanout("net_missing", "BUF_X4_SVT", max_fanout=16)


def test_execute_tcl_script(sample_design, tmp_path):
    eco = ECOEngine(sample_design)
    tcl_file = tmp_path / "test_eco.tcl"
    tcl_file.write_text(
        """
        # Test ECO Tcl Script
        puts "Starting Tcl ECO execution..."
        size_cell u_alu_stage1_fa FA_X2_LVT
        change_cell_type u_alu_stage2_aoi AOI21_X2_LVT
        insert_buffer -net net_mac_stage1 -inst u_tcl_buf_1 -cell BUF_X2_SVT
        insert_buffer -net net_status_fast_1 -inst u_tcl_delay_buf -cell DELAY_CELL_X1_HVT -pin u_reg_status_capture/D
        split_fanout -net ctrl_enable -cell BUF_X4_SVT -max_fanout 16
        puts "Finished Tcl ECO."
        """,
        encoding="utf-8",
    )

    eco.execute_tcl_script(str(tcl_file))
    assert sample_design.instances["u_alu_stage1_fa"].cell_type_name == "FA_X2_LVT"
    assert sample_design.instances["u_alu_stage2_aoi"].cell_type_name == "AOI21_X2_LVT"
    assert "u_tcl_buf_1" in sample_design.instances
    assert "u_tcl_delay_buf" in sample_design.instances
    assert len(eco.eco_history) >= 5


def test_run_automated_timing_closure_custom_target(sample_design):
    eco = ECOEngine(sample_design)
    results = eco.run_automated_timing_closure(
        max_iterations=6,
        target_setup_margin=30.0,
        target_hold_margin=20.0,
    )
    assert "steps" in results
    assert len(results["steps"]) > 0
    assert results["setup_fixed"] is True
    assert results["hold_fixed"] is True
