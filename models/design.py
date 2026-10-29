"""
Circuit netlist and graph representation of a high-frequency Cryptographic MAC Core (1.67 GHz).
Deliberately introduces:
1. Critical Setup Path: 9-stage ALU cone, HVT X1 cells, wire RC -> WNS = -48.97 ps.
2. High Fanout Net (HFN): ctrl_enable driving 65 load pins -> Slew = 91.2 ps (violates 60 ps max limit).
3. Critical Hold Path: Fast LVT buffer + large positive clock skew -> WNS = -17.90 ps.
4. Non-critical path for Power Recovery ECO.
"""

from typing import Optional

from .lib_cells import LIB, CellType


class Net:
    def __init__(self, name: str, wire_cap: float = 2.0, wire_res: float = 0.5):
        self.name = name
        self.driver_pin: Optional[str] = None
        self.sink_pins: list[str] = []
        self.wire_cap = wire_cap # fF
        self.wire_res = wire_res # Ohms

class Instance:
    def __init__(self, name: str, cell_type_name: str):
        self.name = name
        self.cell_type_name = cell_type_name
        self.cell_type: CellType = LIB.get(cell_type_name)
        # Port connections: pin_name -> net_name
        self.connections: dict[str, str] = {}

    def change_cell_type(self, new_cell_type_name: str):
        self.cell_type_name = new_cell_type_name
        self.cell_type = LIB.get(new_cell_type_name)

class CircuitDesign:
    def __init__(self, name: str, clk_period: float = 600.0):
        self.name = name
        self.clk_period = clk_period # 600 ps = 1.667 GHz target
        self.instances: dict[str, Instance] = {}
        self.nets: dict[str, Net] = {}
        self.clock_port = "clk"
        self.clock_uncertainty_setup = 35.0 # ps (jitter + margin)
        self.clock_uncertainty_hold = 20.0  # ps
        self.t_setup_ff = 30.0 # ps
        self.t_hold_ff = 15.0  # ps

    def add_instance(self, inst_name: str, cell_type_name: str) -> Instance:
        inst = Instance(inst_name, cell_type_name)
        self.instances[inst_name] = inst
        return inst

    def get_or_create_net(self, net_name: str, wire_cap: float = 2.0) -> Net:
        if net_name not in self.nets:
            self.nets[net_name] = Net(net_name, wire_cap=wire_cap)
        return self.nets[net_name]

    def connect(self, inst_name: str, pin: str, net_name: str, is_driver: bool = False):
        inst = self.instances[inst_name]
        inst.connections[pin] = net_name
        net = self.get_or_create_net(net_name)
        full_pin_name = f"{inst_name}/{pin}"
        if is_driver:
            net.driver_pin = full_pin_name
        else:
            if full_pin_name not in net.sink_pins:
                net.sink_pins.append(full_pin_name)

    def disconnect_pin(self, inst_name: str, pin: str):
        if inst_name in self.instances and pin in self.instances[inst_name].connections:
            net_name = self.instances[inst_name].connections[pin]
            full_pin_name = f"{inst_name}/{pin}"
            if net_name in self.nets:
                if full_pin_name in self.nets[net_name].sink_pins:
                    self.nets[net_name].sink_pins.remove(full_pin_name)
                if self.nets[net_name].driver_pin == full_pin_name:
                    self.nets[net_name].driver_pin = None
            del self.instances[inst_name].connections[pin]

    def compute_net_load(self, net_name: str) -> float:
        net = self.nets[net_name]
        total_cap = net.wire_cap
        for sink in net.sink_pins:
            inst_name, pin = sink.split("/")
            inst = self.instances[inst_name]
            total_cap += inst.cell_type.input_cap
        return total_cap

def build_high_perf_mac_design() -> CircuitDesign:
    """
    Constructs a 1.67 GHz Cryptographic MAC Unit netlist with active violations:
    1. Critical Setup Path: 9-stage ALU cone, weak X1 HVT cells -> severe negative slack (WNS < 0).
    2. High Fanout Net (HFN): ctrl_enable driving 64 gates -> high load cap & slew violation.
    3. Critical Hold Path: Fast single buffer LVT bypass + clock skew -> hold violation.
    """
    design = CircuitDesign("Crypto_MAC_Unit", clk_period=600.0)

    # ----------------------------------------------------
    # 1. Clock Network (Common root -> Launch & Capture branches)
    # ----------------------------------------------------
    # Common root: u_clk_root
    design.add_instance("u_clk_root", "BUF_X4_SVT")
    design.connect("u_clk_root", "A", "clk")
    design.connect("u_clk_root", "Y", "net_clk_common", is_driver=True)
    design.nets["net_clk_common"].wire_cap = 5.0

    # Launch Clock Branch: Fast short clock path (1 buffer)
    design.add_instance("u_clk_launch_1", "BUF_X4_SVT")
    design.connect("u_clk_launch_1", "A", "net_clk_common")
    design.connect("u_clk_launch_1", "Y", "clk_launch", is_driver=True)
    design.nets["clk_launch"].wire_cap = 4.0

    # Capture Clock Branch: Longer clock tree branch (3 stages -> positive clock skew = +65 ps)
    design.add_instance("u_clk_capture_1", "BUF_X4_SVT")
    design.connect("u_clk_capture_1", "A", "net_clk_common")
    design.connect("u_clk_capture_1", "Y", "net_clk_cap_mid1", is_driver=True)

    design.add_instance("u_clk_capture_2", "BUF_X2_SVT")
    design.connect("u_clk_capture_2", "A", "net_clk_cap_mid1")
    design.connect("u_clk_capture_2", "Y", "net_clk_cap_mid2", is_driver=True)

    design.add_instance("u_clk_capture_3", "BUF_X2_SVT")
    design.connect("u_clk_capture_3", "A", "net_clk_cap_mid2")
    design.connect("u_clk_capture_3", "Y", "clk_capture", is_driver=True)
    design.nets["clk_capture"].wire_cap = 6.0

    # ----------------------------------------------------
    # 2. Critical Setup Path: 9-Stage ALU Execution Cone
    # ----------------------------------------------------
    design.add_instance("u_reg_launch_a", "DFF_X1_SVT")
    design.connect("u_reg_launch_a", "CK", "clk_launch")
    design.connect("u_reg_launch_a", "Q", "net_mac_stage0", is_driver=True)
    design.nets["net_mac_stage0"].wire_cap = 3.5

    # 9 logic stages: Deliberately configured as HVT X1 cells with high wire capacitance
    stages = [
        ("u_alu_stage1_fa",    "FA_X1_HVT",    "A",  "net_mac_stage0", "S", "net_mac_stage1", 5.0),
        ("u_alu_stage2_aoi",   "AOI21_X1_HVT", "A1", "net_mac_stage1", "Y", "net_mac_stage2", 4.5),
        ("u_alu_stage3_xor",   "XOR2_X1_HVT",  "A",  "net_mac_stage2", "Y", "net_mac_stage3", 5.0),
        ("u_alu_stage4_and",   "AND2_X1_HVT",  "A",  "net_mac_stage3", "Y", "net_mac_stage4", 4.0),
        ("u_alu_stage5_mux",   "MUX2_X1_HVT",  "I0", "net_mac_stage4", "Y", "net_mac_stage5", 5.5),
        ("u_alu_stage6_or",    "OR2_X1_HVT",   "A",  "net_mac_stage5", "Y", "net_mac_stage6", 4.0),
        ("u_alu_stage7_nand",  "NAND2_X1_HVT", "A",  "net_mac_stage6", "Y", "net_mac_stage7", 3.5),
        ("u_alu_stage8_xor",   "XOR2_X1_HVT",  "A",  "net_mac_stage7", "Y", "net_mac_stage8", 5.0),
        ("u_alu_stage9_and",   "AND2_X1_HVT",  "A",  "net_mac_stage8", "Y", "net_mac_stage9", 3.5),
    ]

    for inst_name, cell_type, in_pin, in_net, out_pin, out_net, wire_cap in stages:
        design.add_instance(inst_name, cell_type)
        design.connect(inst_name, in_pin, in_net)
        design.connect(inst_name, out_pin, out_net, is_driver=True)
        design.nets[out_net].wire_cap = wire_cap

    # Capture Register
    design.add_instance("u_reg_capture_acc", "DFF_X1_SVT")
    design.connect("u_reg_capture_acc", "CK", "clk_capture")
    design.connect("u_reg_capture_acc", "D", "net_mac_stage9")

    # ----------------------------------------------------
    # 3. High Fanout Net (HFN): Global Enable Control Path
    # ----------------------------------------------------
    design.add_instance("u_reg_ctrl_enable", "DFF_X1_SVT")
    design.connect("u_reg_ctrl_enable", "CK", "clk_launch")
    design.connect("u_reg_ctrl_enable", "Q", "net_ctrl_enable_raw", is_driver=True)

    # Weak X1 driver driving 64 sink gates across the die
    design.add_instance("u_ctrl_drv", "BUF_X1_SVT")
    design.connect("u_ctrl_drv", "A", "net_ctrl_enable_raw")
    design.connect("u_ctrl_drv", "Y", "ctrl_enable", is_driver=True)

    # Net ctrl_enable has large distribution wire capacitance
    design.get_or_create_net("ctrl_enable", wire_cap=110.0)

    # 64 load gates
    for i in range(64):
        dummy_name = f"u_dummy_gate_{i}"
        design.add_instance(dummy_name, "AND2_X1_SVT")
        design.connect(dummy_name, "B", "ctrl_enable")

    # Connect to stage 4 of ALU critical path to directly impact its slew & delay
    design.connect("u_alu_stage4_and", "B", "ctrl_enable")

    # ----------------------------------------------------
    # 4. Critical Hold Path: Fast Bypass / Status Flag
    # ----------------------------------------------------
    # Launch status register
    design.add_instance("u_reg_status_launch", "DFF_X1_SVT")
    design.connect("u_reg_status_launch", "CK", "clk_launch")
    design.connect("u_reg_status_launch", "Q", "net_status_fast_0", is_driver=True)

    # Ultra-fast single LVT inverter/buffer with minimum wire length
    design.add_instance("u_buf_status_fast", "INV_X8_LVT")
    design.connect("u_buf_status_fast", "A", "net_status_fast_0")
    design.connect("u_buf_status_fast", "Y", "net_status_fast_1", is_driver=True)
    design.nets["net_status_fast_1"].wire_cap = 0.5

    # Capture status register (receives late capture clock -> severe hold violation!)
    design.add_instance("u_reg_status_capture", "DFF_X1_SVT")
    design.connect("u_reg_status_capture", "CK", "clk_capture")
    design.connect("u_reg_status_capture", "D", "net_status_fast_1")

    # ----------------------------------------------------
    # 5. Non-Critical Path (Positive Slack for Leakage Power Recovery)
    # ----------------------------------------------------
    design.add_instance("u_reg_non_crit_launch", "DFF_X1_SVT")
    design.connect("u_reg_non_crit_launch", "CK", "clk_launch")
    design.connect("u_reg_non_crit_launch", "Q", "net_noncrit_0", is_driver=True)

    design.add_instance("u_noncrit_inv1", "INV_X8_LVT") # Oversized & LVT (wasting leakage power!)
    design.connect("u_noncrit_inv1", "A", "net_noncrit_0")
    design.connect("u_noncrit_inv1", "Y", "net_noncrit_1", is_driver=True)

    design.add_instance("u_noncrit_inv2", "INV_X8_LVT") # Oversized & LVT
    design.connect("u_noncrit_inv2", "A", "net_noncrit_1")
    design.connect("u_noncrit_inv2", "Y", "net_noncrit_2", is_driver=True)

    design.add_instance("u_reg_non_crit_capture", "DFF_X1_SVT")
    design.connect("u_reg_non_crit_capture", "CK", "clk_capture")
    design.connect("u_reg_non_crit_capture", "D", "net_noncrit_2")

    return design
