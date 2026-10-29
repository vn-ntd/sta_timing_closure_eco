# Advanced Static Timing Analysis (STA) & Timing Closure / ECO Framework

[![CI](https://github.com/vn-ntd/sta_timing_closure_eco/actions/workflows/ci.yml/badge.svg)](https://github.com/vn-ntd/sta_timing_closure_eco/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Field: VLSI / ASIC Design](https://img.shields.io/badge/Domain-VLSI%20%2F%20STA%20%2F%20ECO-orange.svg)](#)
[![Status: Validated on synthetic design](https://img.shields.io/badge/Timing%20ECO-Validated%20on%20synthetic%20design-blue.svg)](#)

> [!NOTE]
> **Scope & Educational Modeling Notice:**  
> This framework is an analytical and algorithmic modeling framework for **Static Timing Analysis (STA)**, **Timing ECO closure**, and **On-Chip Variation (OCV / CRPR / Clock Jitter)** physics built in pure Python. It simulates Non-Linear Delay Models (NLDM), cell sizing trade-offs, and generates industry-compatible Tcl scripts (`size_cell`, `insert_buffer`, `split_fanout`). It is designed for VLSI EDA education, CAD algorithm research, and timing physics exploration, rather than replacing commercial signoff tools (e.g. Synopsys PrimeTime or Cadence Tempus).

A comprehensive simulation and analysis framework for **Static Timing Analysis (STA)**, **Timing Closure via Engineering Change Order (ECO)**, and **On-Chip Variation (OCV / CRPR / Clock Jitter)** modeling in high-speed deep submicron digital ASIC designs.

---

## 🚀 Key Highlights & Capabilities

- **High-Performance Target Design**: 1.667 GHz ($T_{clk} = 600\text{ ps}$) Cryptographic MAC Unit (`Crypto_MAC_Unit`) with deliberate real-world timing violations.
- **Realistic Standard Cell Library**: Non-Linear Delay Model (NLDM), multiple drive strengths ($X1, X2, X4, X8$), and threshold voltage variants ($LVT, SVT, HVT$) with accurate subthreshold leakage and delay trade-offs.
- **Synopsys PrimeTime-Compatible Timing Reports**: Full clock expanded path reporting, displaying point-to-point pin delays, transition slew, load capacitance, cell types, OCV derates, CRPR credit, and library setup/hold margins.
- **Production-Grade Tcl ECO Scripting**: Compatible with Synopsys PrimeTime-ECO, Cadence Tempus, and OpenROAD OpenSTA (`size_cell`, `change_cell_type`, `insert_buffer`, `split_fanout`).
- **Automated Algorithmic ECO Engine**: Heuristic multi-objective optimizer performing sensitivity-based sizing, VT-swapping, hold delay sizing, and leakage power recovery.
- **In-Depth OCV & Jitter Physics**: Exact analytical derivation and empirical sweeping of Flat OCV derates ($0\% - 16\%$), Clock Reconvergence Pessimism Removal (CRPR), and linear Clock Jitter sensitivities.

---

## 📁 Repository Structure

```text
.
├── .github/
│   └── workflows/ci.yml           # GitHub Actions CI matrix workflow
├── docs/
│   └── STA_TIMING_REPORT.md       # Comprehensive analytical signoff report
├── models/
│   ├── __init__.py                # Package exports
│   ├── lib_cells.py               # Standard cell library (NLDM, VT scaling, delay models)
│   ├── design.py                  # 1.67 GHz Crypto MAC netlist & clock distribution tree
│   ├── sta_engine.py              # STA engine (forward propagation, OCV, CRPR, report generator)
│   └── eco_engine.py              # ECO parser & automated timing closure optimizer
├── tcl_scripts/
│   └── eco_manual.tcl             # Industry-standard Tcl ECO script
├── tests/
│   ├── test_sta_engine.py         # STA engine, slack equations, CRPR & Jitter tests
│   ├── test_eco_engine.py         # Sizing, buffer insertion, split_fanout & Tcl execution tests
│   ├── test_lib_cells.py          # NLDM models, VT scaling & cell characteristics tests
│   ├── test_design.py             # Design connectivity & netlist graph tests
│   └── test_cli.py                # CLI interface & JSON/CSV export tests
├── run_experiments.py             # Master experiment runner (CLI, OCV & Jitter sweeps, exports)
├── run_auto_eco.py                # Standalone automated algorithmic ECO runner
├── pyproject.toml                 # Modern PEP 517/518 build metadata & tool configs
├── requirements.txt               # Core runtime environment declaration
├── requirements-dev.txt           # Development & testing dependencies
├── LICENSE                        # MIT License
└── README.md                      # Project documentation
```

---

## 🔬 Mathematical Formulations

### 1. Setup & Hold Slack Equations

$$\mathbf{Slack_{setup}} = (T_{clk} + T_{capture\_early} + CRPR - T_{uncertainty\_setup} - T_{setup\_ff}) - (T_{launch\_late} + T_{cq\_late} + T_{data\_late})$$

$$\mathbf{Slack_{hold}} = (T_{launch\_early} + T_{cq\_early} + T_{data\_early}) - (T_{capture\_late} - CRPR + T_{uncertainty\_hold} + T_{hold\_ff})$$

### 2. Clock Reconvergence Pessimism Removal (CRPR)

In the presence of flat OCV derating ($\alpha_{late} > 1.0, \alpha_{early} < 1.0$), the common clock root physically executes on a single silicon gate per cycle. Applying conflicting derating factors creates artificial pessimism, compensated by:

$$CRPR = T_{common\_unskewed} \times |\alpha_{late} - \alpha_{early}|$$

### 3. Clock Jitter Sensitivities

$$\frac{\partial (Slack_{setup})}{\partial (Jitter)} = -1.00\text{ ps/ps}, \quad \frac{\partial (Slack_{hold})}{\partial (Jitter)} = -0.50\text{ ps/ps}$$

---

## 📊 Summary of Closure Results

| Metric | Baseline (Pre-ECO) | Post-ECO | Delta ($\Delta$) | Signoff Status |
| :--- | :---: | :---: | :---: | :---: |
| **Setup Slack (WNS)** | **-48.97 ps** | **+212.73 ps** | **+261.70 ps** | **MET (CLOSED)** |
| **Hold Slack (WNS)** | **-17.90 ps** | **+101.81 ps** | **+119.71 ps** | **MET (CLOSED)** |
| **Data Arrival Time (Setup)** | $665.46\text{ ps}$ | $403.76\text{ ps}$ | $-261.70\text{ ps}$ | **$-39.3\%$ delay reduction** |
| **Max Slew Transition** | $91.2\text{ ps}$ (Fail > 60) | $16.5\text{ ps}$ | $-74.70\text{ ps}$ | **MET** |
| **Max Fanout** | $65$ loads (Fail > 16) | $16$ loads/branch | $-49$ loads | **MET** |
| **Leakage Power** | $15.940\ \mu\text{W}$ | $32.155\ \mu\text{W}$ | $+16.215\ \mu\text{W}$ | Controlled VT trade-off |
| **Standard Cell Area** | $181.36\ \mu\text{m}^2$ | $217.83\ \mu\text{m}^2$ | $+36.47\ \mu\text{m}^2$ | $+20.1\%$ layout penalty |

---

## 🛠️ Quick Start & Execution

### 1. Clone & Setup
```bash
git clone https://github.com/vn-ntd/sta_timing_closure_eco.git
cd sta_timing_closure_eco

# Install package in editable mode with development dependencies
pip install -e ".[dev]"
```

### 2. Run Comprehensive Experiments
Executes baseline STA, applies `tcl_scripts/eco_manual.tcl`, verifies signoff closure, and runs OCV and Clock Jitter sweeps:
```bash
python run_experiments.py
```

Advanced CLI options with structured data export:
```bash
# Export signoff summary to JSON and sweep tables to CSV
python run_experiments.py --quiet --export-json reports/timing_summary.json --export-csv reports/sweep

# Customize OCV derate factors and clock jitter
python run_experiments.py --derate-late 1.10 --derate-early 0.90 --jitter 25.0
```

### 3. Run Automated Algorithmic ECO
Demonstrates automated iterative timing closure:
```bash
python run_auto_eco.py
```

### 4. Run Verification Tests & Coverage
```bash
# Run 25 unit tests with line and branch coverage (>92% coverage)
pytest --cov=models tests/
```

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
