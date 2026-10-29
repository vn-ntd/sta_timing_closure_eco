
from models.design import CircuitDesign, Instance, build_high_perf_mac_design


def test_circuit_design_basic_connectivity():
    design = CircuitDesign("Simple_Core", clk_period=500.0)
    assert design.name == "Simple_Core"
    assert design.clk_period == 500.0

    inst = design.add_instance("u_inv1", "INV_X1_SVT")
    assert inst.name == "u_inv1"
    assert inst.cell_type_name == "INV_X1_SVT"

    # Connect driver and sink
    design.connect("u_inv1", "Y", "net_test", is_driver=True)
    design.add_instance("u_inv2", "INV_X1_SVT")
    design.connect("u_inv2", "A", "net_test", is_driver=False)

    net = design.nets["net_test"]
    assert net.driver_pin == "u_inv1/Y"
    assert "u_inv2/A" in net.sink_pins


def test_instance_change_cell_type():
    inst = Instance("u_gate", "AND2_X1_HVT")
    assert inst.cell_type.drive_strength == 1
    assert inst.cell_type.vt == "HVT"

    inst.change_cell_type("AND2_X4_LVT")
    assert inst.cell_type_name == "AND2_X4_LVT"
    assert inst.cell_type.drive_strength == 4
    assert inst.cell_type.vt == "LVT"


def test_build_high_perf_mac_design():
    design = build_high_perf_mac_design()
    assert design.name == "Crypto_MAC_Unit"
    assert design.clk_period == 600.0
    assert len(design.instances) >= 80
    assert "ctrl_enable" in design.nets
    assert len(design.nets["ctrl_enable"].sink_pins) == 65
    assert "u_clk_root" in design.instances
    assert "u_clk_launch_1" in design.instances
    assert "u_clk_capture_3" in design.instances
