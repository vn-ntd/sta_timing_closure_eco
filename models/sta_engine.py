"""
Static Timing Analysis (STA) Engine with OCV derating, CRPR, clock jitter,
dynamic path tracing, and PrimeTime-compatible timing report generator.
"""

from dataclasses import dataclass
from typing import Optional

from .design import CircuitDesign, Net
from .lib_cells import LIB


@dataclass
class TimingPoint:
    pin_name: str
    cell_name: str
    cell_type: str
    incr_delay: float
    path_delay: float
    slew: float
    load_cap: float
    derate: float

@dataclass
class TimingPathReport:
    path_name: str
    path_type: str        # "max" (setup) or "min" (hold)
    startpoint: str
    endpoint: str
    clock_period: float
    clock_uncertainty: float
    crpr_credit: float
    arrival_points: list[TimingPoint]
    capture_points: list[TimingPoint]
    data_arrival_time: float
    data_required_time: float
    slack: float
    violation: bool

class STACondition:
    def __init__(self, late_derate: float = 1.08, early_derate: float = 0.92,
                 jitter: float = 20.0, margin: float = 15.0, enable_crpr: bool = True):
        self.late_derate = late_derate
        self.early_derate = early_derate
        self.jitter = jitter     # ps
        self.margin = margin     # ps
        self.enable_crpr = enable_crpr

class STAEngine:
    def __init__(self, design: CircuitDesign, condition: Optional[STACondition] = None):
        self.design = design
        self.condition = condition if condition else STACondition()

    def _get_wire_elmore_delay(self, net: Net) -> float:
        sinks_cap = 0.0
        for sink in net.sink_pins:
            inst_name, _ = sink.split("/")
            inst = self.design.instances[inst_name]
            sinks_cap += inst.cell_type.input_cap
        elmore = (0.5 * net.wire_res * net.wire_cap) + (net.wire_res * sinks_cap)
        return round(elmore * 0.001, 2)

    def analyze_clock_network(self, clk_type: str) -> tuple[float, float, float, list[TimingPoint], list[TimingPoint]]:
        cond = self.condition
        derate_launch = cond.late_derate if clk_type == "max" else cond.early_derate
        derate_capture = cond.early_derate if clk_type == "max" else cond.late_derate

        launch_pts = []
        capture_pts = []

        # Common root: u_clk_root
        inst_root = self.design.instances["u_clk_root"]
        load_root = self.design.compute_net_load("net_clk_common")
        root_delay_nom, root_slew = LIB.calculate_cell_delay_and_slew(inst_root.cell_type, 15.0, load_root)

        # Launch branch: u_clk_launch_1
        inst_launch1 = self.design.instances["u_clk_launch_1"]
        load_launch1 = self.design.compute_net_load("clk_launch")
        l1_delay_nom, l1_slew = LIB.calculate_cell_delay_and_slew(inst_launch1.cell_type, root_slew, load_launch1)

        # Capture branch: u_clk_capture_1 -> u_clk_capture_2 -> u_clk_capture_3
        inst_cap1 = self.design.instances["u_clk_capture_1"]
        load_cap1 = self.design.compute_net_load("net_clk_cap_mid1")
        c1_delay_nom, c1_slew = LIB.calculate_cell_delay_and_slew(inst_cap1.cell_type, root_slew, load_cap1)

        inst_cap2 = self.design.instances["u_clk_capture_2"]
        load_cap2 = self.design.compute_net_load("net_clk_cap_mid2")
        c2_delay_nom, c2_slew = LIB.calculate_cell_delay_and_slew(inst_cap2.cell_type, c1_slew, load_cap2)

        inst_cap3 = self.design.instances["u_clk_capture_3"]
        load_cap3 = self.design.compute_net_load("clk_capture")
        c3_delay_nom, c3_slew = LIB.calculate_cell_delay_and_slew(inst_cap3.cell_type, c2_slew, load_cap3)

        # Apply derates
        t_root_launch = root_delay_nom * derate_launch
        t_l1 = l1_delay_nom * derate_launch
        t_launch_total = t_root_launch + t_l1

        t_root_capture = root_delay_nom * derate_capture
        t_c1 = c1_delay_nom * derate_capture
        t_c2 = c2_delay_nom * derate_capture
        t_c3 = c3_delay_nom * derate_capture
        t_capture_total = t_root_capture + t_c1 + t_c2 + t_c3

        # CRPR: Common clock path is u_clk_root
        if cond.enable_crpr:
            crpr_credit = root_delay_nom * abs(cond.late_derate - cond.early_derate)
        else:
            crpr_credit = 0.0

        # Launch points
        launch_pts.append(TimingPoint("clk", "source", "port", 0.0, 0.0, 15.0, 0.0, 1.0))
        launch_pts.append(TimingPoint("u_clk_root/Y", "u_clk_root", inst_root.cell_type_name,
                                      round(t_root_launch, 2), round(t_root_launch, 2), round(root_slew, 2), load_root, derate_launch))
        launch_pts.append(TimingPoint("u_clk_launch_1/Y (clk_launch)", "u_clk_launch_1", inst_launch1.cell_type_name,
                                      round(t_l1, 2), round(t_launch_total, 2), round(l1_slew, 2), load_launch1, derate_launch))

        # Capture points
        capture_pts.append(TimingPoint("clk", "source", "port", 0.0, 0.0, 15.0, 0.0, 1.0))
        capture_pts.append(TimingPoint("u_clk_root/Y", "u_clk_root", inst_root.cell_type_name,
                                       round(t_root_capture, 2), round(t_root_capture, 2), round(root_slew, 2), load_root, derate_capture))
        capture_pts.append(TimingPoint("u_clk_capture_1/Y", "u_clk_capture_1", inst_cap1.cell_type_name,
                                       round(t_c1, 2), round(t_root_capture + t_c1, 2), round(c1_slew, 2), load_cap1, derate_capture))
        capture_pts.append(TimingPoint("u_clk_capture_2/Y", "u_clk_capture_2", inst_cap2.cell_type_name,
                                       round(t_c2, 2), round(t_root_capture + t_c1 + t_c2, 2), round(c2_slew, 2), load_cap2, derate_capture))
        capture_pts.append(TimingPoint("u_clk_capture_3/Y (clk_capture)", "u_clk_capture_3", inst_cap3.cell_type_name,
                                       round(t_c3, 2), round(t_capture_total, 2), round(c3_slew, 2), load_cap3, derate_capture))

        return t_launch_total, t_capture_total, crpr_credit, launch_pts, capture_pts

    def _trace_data_chain(self, start_inst: str, end_inst: str, clk_launch_delay: float, initial_slew: float, derate: float) -> tuple[float, list[TimingPoint]]:
        """
        Dynamically traverses from start flip-flop Q pin through combinational gates/buffers to endpoint D pin.
        """
        pts = []
        curr_time = clk_launch_delay
        curr_slew = initial_slew

        # Launch FF Clock-to-Q
        launch_ff = self.design.instances[start_inst]
        q_net_name = launch_ff.connections["Q"]
        load_q = self.design.compute_net_load(q_net_name)
        cq_delay_nom, curr_slew = LIB.calculate_cell_delay_and_slew(launch_ff.cell_type, curr_slew, load_q)
        cq_delay = cq_delay_nom * derate
        curr_time += cq_delay
        pts.append(TimingPoint(f"{start_inst}/Q", start_inst, launch_ff.cell_type_name,
                               round(cq_delay, 2), round(curr_time, 2), round(curr_slew, 2), load_q, derate))

        # Follow net connectivity
        curr_net_name = q_net_name
        visited_instances = {start_inst}

        while True:
            curr_net = self.design.nets[curr_net_name]
            # Find next gate driven by this net that leads towards end_inst
            next_inst_name = None
            for sink in curr_net.sink_pins:
                inst_name, pin = sink.split("/")
                if inst_name not in visited_instances and inst_name != end_inst:
                    # Found next combinational cell
                    next_inst_name = inst_name
                    break
                elif inst_name == end_inst:
                    # Reached endpoint flip-flop D pin!
                    return curr_time, pts

            if not next_inst_name:
                break

            visited_instances.add(next_inst_name)
            inst = self.design.instances[next_inst_name]

            # Find output pin and driving net
            out_pin = "Y" if "Y" in inst.connections else ("S" if "S" in inst.connections else "Q")
            out_net_name = inst.connections.get(out_pin)
            if not out_net_name:
                break

            out_net = self.design.nets[out_net_name]
            load_cap = self.design.compute_net_load(out_net_name)
            wire_delay = self._get_wire_elmore_delay(out_net) * derate

            # Impact of HFN if connected
            extra_slew = 0.0
            if "B" in inst.connections and inst.connections["B"] == "ctrl_enable":
                hfn_load = self.design.compute_net_load("ctrl_enable")
                extra_slew = min(hfn_load * 0.28, 55.0)

            d_nom, curr_slew = LIB.calculate_cell_delay_and_slew(inst.cell_type, curr_slew + extra_slew, load_cap)
            cell_delay = (d_nom + wire_delay) * derate
            curr_time += cell_delay

            pts.append(TimingPoint(f"{next_inst_name}/{out_pin}", next_inst_name, inst.cell_type_name,
                                   round(cell_delay, 2), round(curr_time, 2), round(curr_slew, 2), load_cap, derate))
            curr_net_name = out_net_name

        return curr_time, pts

    def analyze_setup_critical_path(self) -> TimingPathReport:
        cond = self.condition
        derate_data = cond.late_derate
        uncertainty = cond.jitter + cond.margin

        t_launch_clk, t_capture_clk, crpr, launch_pts, capture_pts = self.analyze_clock_network("max")

        # Dynamic trace through ALU pipeline
        data_arr, data_pts = self._trace_data_chain("u_reg_launch_a", "u_reg_capture_acc", t_launch_clk, launch_pts[-1].slew, derate_data)
        all_arrival_pts = launch_pts + data_pts

        t_setup_ff = self.design.t_setup_ff
        data_required_time = self.design.clk_period + t_capture_clk - t_setup_ff - uncertainty + crpr
        slack = data_required_time - data_arr

        return TimingPathReport(
            path_name="Path: u_reg_launch_a -> u_reg_capture_acc (ALU Critical Setup)",
            path_type="max",
            startpoint="u_reg_launch_a/CK (rising edge-triggered flip-flop)",
            endpoint="u_reg_capture_acc/D (rising edge-triggered flip-flop)",
            clock_period=self.design.clk_period,
            clock_uncertainty=uncertainty,
            crpr_credit=crpr,
            arrival_points=all_arrival_pts,
            capture_points=capture_pts,
            data_arrival_time=round(data_arr, 2),
            data_required_time=round(data_required_time, 2),
            slack=round(slack, 2),
            violation=(slack < 0.0)
        )

    def analyze_hold_critical_path(self) -> TimingPathReport:
        cond = self.condition
        derate_data = cond.early_derate
        uncertainty = cond.jitter * 0.5 + 5.0 # ps

        t_launch_clk, t_capture_clk, crpr, launch_pts, capture_pts = self.analyze_clock_network("min")

        data_arr, data_pts = self._trace_data_chain("u_reg_status_launch", "u_reg_status_capture", t_launch_clk, launch_pts[-1].slew, derate_data)
        all_arrival_pts = launch_pts + data_pts

        t_hold_ff = self.design.t_hold_ff
        data_required_time = t_capture_clk + t_hold_ff + uncertainty - crpr
        slack = data_arr - data_required_time

        return TimingPathReport(
            path_name="Path: u_reg_status_launch -> u_reg_status_capture (Status Flag Hold)",
            path_type="min",
            startpoint="u_reg_status_launch/CK (rising edge-triggered flip-flop)",
            endpoint="u_reg_status_capture/D (rising edge-triggered flip-flop)",
            clock_period=self.design.clk_period,
            clock_uncertainty=uncertainty,
            crpr_credit=crpr,
            arrival_points=all_arrival_pts,
            capture_points=capture_pts,
            data_arrival_time=round(data_arr, 2),
            data_required_time=round(data_required_time, 2),
            slack=round(slack, 2),
            violation=(slack < 0.0)
        )

    def analyze_non_critical_path(self) -> TimingPathReport:
        cond = self.condition
        derate_data = cond.late_derate
        uncertainty = cond.jitter + cond.margin

        t_launch_clk, t_capture_clk, crpr, launch_pts, capture_pts = self.analyze_clock_network("max")
        data_arr, data_pts = self._trace_data_chain("u_reg_non_crit_launch", "u_reg_non_crit_capture", t_launch_clk, launch_pts[-1].slew, derate_data)

        t_setup_ff = self.design.t_setup_ff
        data_required_time = self.design.clk_period + t_capture_clk - t_setup_ff - uncertainty + crpr
        slack = data_required_time - data_arr

        return TimingPathReport(
            path_name="Path: u_reg_non_crit_launch -> u_reg_non_crit_capture (Non-Critical)",
            path_type="max",
            startpoint="u_reg_non_crit_launch/CK",
            endpoint="u_reg_non_crit_capture/D",
            clock_period=self.design.clk_period,
            clock_uncertainty=uncertainty,
            crpr_credit=crpr,
            arrival_points=launch_pts + data_pts,
            capture_points=capture_pts,
            data_arrival_time=round(data_arr, 2),
            data_required_time=round(data_required_time, 2),
            slack=round(slack, 2),
            violation=(slack < 0.0)
        )

    def analyze_high_fanout_nets(self, max_fanout_limit: int = 16, max_slew_limit: float = 60.0) -> list[dict]:
        violations = []
        for net_name, net in self.design.nets.items():
            fanout = len(net.sink_pins)
            total_load = self.design.compute_net_load(net_name)

            driver_cell = "Unknown"
            out_slew = 0.0
            if net.driver_pin:
                drv_inst_name, _ = net.driver_pin.split("/")
                drv_inst = self.design.instances[drv_inst_name]
                driver_cell = drv_inst.cell_type_name
                _, out_slew = LIB.calculate_cell_delay_and_slew(drv_inst.cell_type, 20.0, total_load)

            if fanout > max_fanout_limit or out_slew > max_slew_limit:
                violations.append({
                    "net": net_name,
                    "fanout": fanout,
                    "load_cap_fF": round(total_load, 2),
                    "driver_cell": driver_cell,
                    "transition_slew_ps": round(out_slew, 2),
                    "hfn_violation": fanout > max_fanout_limit,
                    "slew_violation": out_slew > max_slew_limit
                })
        return violations

    def compute_power_and_area(self) -> tuple[float, float]:
        total_leakage = 0.0
        total_area = 0.0
        for inst in self.design.instances.values():
            total_leakage += inst.cell_type.leakage_power
            total_area += inst.cell_type.area
        return round(total_leakage, 3), round(total_area, 2)

    def format_primetime_report(self, path: TimingPathReport) -> str:
        lines = []
        lines.append("=" * 84)
        lines.append(f"  Timing Report: {path.path_name}")
        lines.append("=" * 84)
        lines.append(f"  Design        : {self.design.name}")
        lines.append(f"  Operating Cond: Late Derate={self.condition.late_derate}, Early Derate={self.condition.early_derate}")
        lines.append(f"  Clock Period  : {path.clock_period:.2f} ps (Frequency: {1000000.0/path.clock_period:.2f} MHz)")
        lines.append(f"  Delay Type    : {path.path_type.upper()} ({'Setup' if path.path_type == 'max' else 'Hold'})")
        lines.append(f"  Startpoint    : {path.startpoint}")
        lines.append(f"  Endpoint      : {path.endpoint}")
        lines.append("-" * 84)
        lines.append(f"{'Point':<38} {'Incr(ps)':<10} {'Path(ps)':<10} {'Slew(ps)':<10} {'Cap(fF)':<8} {'Cell'}")
        lines.append("-" * 84)

        for pt in path.arrival_points:
            lines.append(f"{pt.pin_name:<38} {pt.incr_delay:>8.2f}  {pt.path_delay:>8.2f}  {pt.slew:>8.2f}  {pt.load_cap:>6.1f}   {pt.cell_type}")

        lines.append("-" * 84)
        lines.append(f"  data arrival time                                      {path.data_arrival_time:>10.2f}")
        lines.append("")

        if path.path_type == "max":
            lines.append(f"  clock clk (rise edge)                                  {path.clock_period:>10.2f}")
            lines.append(f"  clock network delay (capture early)                    {path.capture_points[-1].path_delay:>10.2f}")
            lines.append(f"  clock reconvergence pessimism (CRPR)                   {path.crpr_credit:>10.2f}")
            lines.append(f"  clock uncertainty (jitter + margin)                    {-path.clock_uncertainty:>10.2f}")
            lines.append(f"  library setup time                                     {-self.design.t_setup_ff:>10.2f}")
            lines.append(f"  data required time                                     {path.data_required_time:>10.2f}")
            lines.append("-" * 84)
            lines.append(f"  data required time                                     {path.data_required_time:>10.2f}")
            lines.append(f"  data arrival time                                     {-path.data_arrival_time:>10.2f}")
            lines.append("-" * 84)
            status = "VIOLATED" if path.violation else "MET"
            lines.append(f"  slack ({status})                                          {path.slack:>10.2f} ps")
        else:
            lines.append("  clock clk (rise edge)                                        0.00")
            lines.append(f"  clock network delay (capture late)                     {path.capture_points[-1].path_delay:>10.2f}")
            lines.append(f"  clock reconvergence pessimism (CRPR)                   {-path.crpr_credit:>10.2f}")
            lines.append(f"  clock uncertainty (jitter)                             {path.clock_uncertainty:>10.2f}")
            lines.append(f"  library hold time                                      {self.design.t_hold_ff:>10.2f}")
            lines.append(f"  data required time                                     {path.data_required_time:>10.2f}")
            lines.append("-" * 84)
            lines.append(f"  data arrival time                                      {path.data_arrival_time:>10.2f}")
            lines.append(f"  data required time                                    {-path.data_required_time:>10.2f}")
            lines.append("-" * 84)
            status = "VIOLATED" if path.violation else "MET"
            lines.append(f"  slack ({status})                                          {path.slack:>10.2f} ps")
        lines.append("=" * 84)
        return "\n".join(lines)
