"""
Industrial standard cell library definition for STA & ECO timing closure.
Provides realistic Non-Linear Delay Models (NLDM), pin capacitances,
VT variants (LVT, SVT, HVT), and drive strengths (X1, X2, X4, X8).
"""

from dataclasses import dataclass
from typing import Dict, Tuple

@dataclass
class CellType:
    name: str
    base_name: str       # e.g., "AND2", "INV", "BUF", "DFF"
    drive_strength: int  # 1, 2, 4, 8
    vt: str              # "LVT", "SVT", "HVT"
    input_cap: float     # fF (femtofarads)
    base_delay: float    # ps (picoseconds) intrinsic delay
    drive_res: float     # ps / fF (delay per load cap)
    slew_sens: float     # ps / ps (delay sensitivity to input slew)
    slew_out_base: float # ps intrinsic output slew
    slew_out_load: float # ps / fF output slew sensitivity to load cap
    leakage_power: float # uW (microwatts)
    area: float          # um^2

# VT delay and leakage scaling factors relative to SVT
# LVT: 30% faster intrinsic & drive, but ~7-8x higher leakage
# HVT: 35% slower, but ~90% lower leakage (ideal for non-critical paths)
VT_FACTORS = {
    "LVT": {"delay": 0.72, "leakage": 7.50},
    "SVT": {"delay": 1.00, "leakage": 1.00},
    "HVT": {"delay": 1.35, "leakage": 0.12},
}

BASE_CELL_SPECS = {
    "INV": {
        "base_delay": 12.0, "drive_res": 0.28, "input_cap": 1.2,
        "slew_sens": 0.10, "slew_out_base": 10.0, "slew_out_load": 0.22,
        "base_leakage": 0.05, "base_area": 0.8
    },
    "BUF": {
        "base_delay": 20.0, "drive_res": 0.24, "input_cap": 1.4,
        "slew_sens": 0.12, "slew_out_base": 12.0, "slew_out_load": 0.20,
        "base_leakage": 0.08, "base_area": 1.2
    },
    "DELAY_CELL": {
        "base_delay": 95.0, "drive_res": 0.35, "input_cap": 1.5,
        "slew_sens": 0.15, "slew_out_base": 15.0, "slew_out_load": 0.25,
        "base_leakage": 0.09, "base_area": 1.8
    },
    "AND2": {
        "base_delay": 28.0, "drive_res": 0.32, "input_cap": 1.6,
        "slew_sens": 0.14, "slew_out_base": 14.0, "slew_out_load": 0.26,
        "base_leakage": 0.10, "base_area": 1.6
    },
    "NAND2": {
        "base_delay": 22.0, "drive_res": 0.29, "input_cap": 1.5,
        "slew_sens": 0.12, "slew_out_base": 12.0, "slew_out_load": 0.24,
        "base_leakage": 0.08, "base_area": 1.4
    },
    "OR2": {
        "base_delay": 30.0, "drive_res": 0.33, "input_cap": 1.7,
        "slew_sens": 0.15, "slew_out_base": 15.0, "slew_out_load": 0.27,
        "base_leakage": 0.11, "base_area": 1.7
    },
    "XOR2": {
        "base_delay": 42.0, "drive_res": 0.38, "input_cap": 2.2,
        "slew_sens": 0.18, "slew_out_base": 18.0, "slew_out_load": 0.30,
        "base_leakage": 0.18, "base_area": 2.4
    },
    "AOI21": {
        "base_delay": 36.0, "drive_res": 0.34, "input_cap": 2.0,
        "slew_sens": 0.16, "slew_out_base": 16.0, "slew_out_load": 0.28,
        "base_leakage": 0.15, "base_area": 2.2
    },
    "MUX2": {
        "base_delay": 38.0, "drive_res": 0.35, "input_cap": 2.1,
        "slew_sens": 0.16, "slew_out_base": 17.0, "slew_out_load": 0.28,
        "base_leakage": 0.16, "base_area": 2.5
    },
    "FA": { # Full Adder bit slice
        "base_delay": 65.0, "drive_res": 0.42, "input_cap": 3.0,
        "slew_sens": 0.20, "slew_out_base": 22.0, "slew_out_load": 0.32,
        "base_leakage": 0.35, "base_area": 4.8
    },
    "DFF": { # Flip-Flop: base_delay is Clk-to-Q, input_cap is D pin cap
        "base_delay": 55.0, "drive_res": 0.28, "input_cap": 1.8,
        "slew_sens": 0.10, "slew_out_base": 16.0, "slew_out_load": 0.25,
        "base_leakage": 0.25, "base_area": 4.0,
        "t_setup": 35.0, "t_hold": 15.0 # ps
    }
}

class StandardLibrary:
    def __init__(self):
        self.cells: Dict[str, CellType] = {}
        self._build_library()

    def _build_library(self):
        drive_scales = {1: 1.0, 2: 0.55, 4: 0.30, 8: 0.16}
        cap_scales   = {1: 1.0, 2: 1.8,  4: 3.4,  8: 6.2}
        area_scales  = {1: 1.0, 2: 1.7,  4: 3.1,  8: 5.8}

        for base, spec in BASE_CELL_SPECS.items():
            for vt in ["LVT", "SVT", "HVT"]:
                vt_data = VT_FACTORS[vt]
                for drive in [1, 2, 4, 8]:
                    cell_name = f"{base}_X{drive}_{vt}"
                    
                    # Higher drive reduces effective output resistance
                    drive_res = spec["drive_res"] * drive_scales[drive] * vt_data["delay"]
                    base_delay = spec["base_delay"] * vt_data["delay"]
                    in_cap = spec["input_cap"] * cap_scales[drive]
                    leakage = spec["base_leakage"] * area_scales[drive] * vt_data["leakage"]
                    area = spec["base_area"] * area_scales[drive]
                    slew_sens = spec["slew_sens"]
                    slew_out_base = spec["slew_out_base"] * vt_data["delay"]
                    slew_out_load = spec["slew_out_load"] * drive_scales[drive]

                    cell = CellType(
                        name=cell_name,
                        base_name=base,
                        drive_strength=drive,
                        vt=vt,
                        input_cap=round(in_cap, 3),
                        base_delay=round(base_delay, 2),
                        drive_res=round(drive_res, 4),
                        slew_sens=round(slew_sens, 3),
                        slew_out_base=round(slew_out_base, 2),
                        slew_out_load=round(slew_out_load, 4),
                        leakage_power=round(leakage, 4),
                        area=round(area, 2)
                    )
                    self.cells[cell_name] = cell

    def get(self, cell_name: str) -> CellType:
        if cell_name not in self.cells:
            raise KeyError(f"Cell '{cell_name}' not found in standard cell library.")
        return self.cells[cell_name]

    def get_swapped_vt(self, cell_name: str, new_vt: str) -> str:
        parts = cell_name.split("_")
        base = parts[0]
        drive = parts[1]
        target = f"{base}_{drive}_{new_vt}"
        if target in self.cells:
            return target
        raise ValueError(f"Target cell {target} does not exist.")

    def get_resized_cell(self, cell_name: str, new_drive: int) -> str:
        parts = cell_name.split("_")
        base = parts[0]
        vt = parts[2]
        target = f"{base}_X{new_drive}_{vt}"
        if target in self.cells:
            return target
        raise ValueError(f"Target cell {target} does not exist.")

    def calculate_cell_delay_and_slew(self, cell_type: CellType, in_slew: float, load_cap: float) -> Tuple[float, float]:
        """
        NLDM delay formula:
        delay = base_delay + (slew_sens * in_slew) + (drive_res * load_cap)
        out_slew = slew_out_base + 0.05 * in_slew + (slew_out_load * load_cap)
        """
        delay = cell_type.base_delay + (cell_type.slew_sens * in_slew) + (cell_type.drive_res * load_cap)
        out_slew = cell_type.slew_out_base + (0.05 * in_slew) + (cell_type.slew_out_load * load_cap)
        return max(delay, 2.0), max(out_slew, 5.0)

# Instantiate singleton library
LIB = StandardLibrary()
