import pytest

from models.lib_cells import LIB, StandardLibrary


def test_library_initialization_and_lookup():
    lib = StandardLibrary()
    buf_cell = lib.get("BUF_X4_SVT")
    assert buf_cell.base_name == "BUF"
    assert buf_cell.drive_strength == 4
    assert buf_cell.vt == "SVT"

    # Test error handling on missing cell
    with pytest.raises(KeyError, match="not found in standard cell library"):
        lib.get("NONEXISTENT_CELL_X99_XYZ")


def test_vt_scaling_properties():
    # LVT vs SVT vs HVT for same base cell & drive strength
    lvt = LIB.get("INV_X1_LVT")
    svt = LIB.get("INV_X1_SVT")
    hvt = LIB.get("INV_X1_HVT")

    # Delay order: LVT < SVT < HVT
    assert lvt.base_delay < svt.base_delay < hvt.base_delay

    # Leakage power order: HVT < SVT < LVT
    assert hvt.leakage_power < svt.leakage_power < lvt.leakage_power


def test_drive_strength_scaling():
    x1 = LIB.get("AND2_X1_SVT")
    x4 = LIB.get("AND2_X4_SVT")

    # Higher drive strength: lower output resistance, larger area, higher input cap
    assert x4.drive_res < x1.drive_res
    assert x4.area > x1.area
    assert x4.input_cap > x1.input_cap


def test_vt_swapping_utility():
    swapped = LIB.get_swapped_vt("FA_X1_HVT", "LVT")
    assert swapped == "FA_X1_LVT"

    with pytest.raises(ValueError, match="does not exist"):
        LIB.get_swapped_vt("FA_X1_HVT", "INVALID_VT")


def test_cell_resizing_utility():
    resized = LIB.get_resized_cell("OR2_X1_SVT", 4)
    assert resized == "OR2_X4_SVT"

    with pytest.raises(ValueError, match="does not exist"):
        LIB.get_resized_cell("OR2_X1_SVT", 99)


def test_nldm_delay_and_slew_calculation():
    cell = LIB.get("BUF_X2_SVT")
    in_slew = 20.0  # ps
    load_cap = 10.0  # fF

    delay, out_slew = LIB.calculate_cell_delay_and_slew(cell, in_slew, load_cap)
    expected_delay = cell.base_delay + (cell.slew_sens * in_slew) + (cell.drive_res * load_cap)
    expected_slew = cell.slew_out_base + (0.05 * in_slew) + (cell.slew_out_load * load_cap)

    assert delay == pytest.approx(expected_delay, rel=1e-3)
    assert out_slew == pytest.approx(expected_slew, rel=1e-3)
    assert delay >= 2.0
    assert out_slew >= 5.0
