"""Worked examples with published answers, end to end through the engine.

A calculation tool is only worth anything if its numbers are right, so this
file works real examples the way an engineer would type them and checks the
answers against values that can be arrived at independently — by hand, from a
code clause, or from an exact definition.

Every case says where its expected answer comes from. Where a published figure
is rounded, the tolerance here is the rounding, not slack.
"""
import math

import pytest

from calcforge.core.engine import Workspace, evaluate_source


def sheet(source: str) -> Workspace:
    """Evaluate a calculation the way a page of the app does."""
    workspace = Workspace()
    workspace.begin_pass()
    statements = evaluate_source(source, workspace, "validation")
    errors = [(s.raw, s.error) for s in statements if s.error]
    assert errors == [], f"the sheet did not evaluate cleanly: {errors}"
    return workspace


def value(workspace: Workspace, name: str, unit: str) -> float:
    """The value of *name*, read in *unit* — the number an engineer would use."""
    quantity = workspace.get(name)
    assert quantity is not None, f"{name} was never defined"
    if not hasattr(quantity, "to"):          # a ratio that cancelled to a float
        assert unit == "dimensionless", f"{name} came out with no units"
        return float(quantity)
    return float(quantity.to(unit).magnitude)


# ---------------------------------------------------------------------------
# exact definitions — these are not approximations, they are the definitions
# ---------------------------------------------------------------------------

EXACT = [
    ("1 in", "mm", 25.4),                    # international inch, 1959
    ("1 ft", "m", 0.3048),
    ("1 yd", "m", 0.9144),
    ("1 mile", "km", 1.609344),
    ("1 lb", "kg", 0.45359237),
    ("1 tonne", "kg", 1000.0),
    ("1 hour", "s", 3600.0),
    ("1 hectare", "m^2", 10000.0),
    ("1 litre", "m^3", 0.001),
    ("1 bar", "kPa", 100.0),
    ("1 MPa", "N/mm^2", 1.0),                # the identity every engineer uses
    ("1 kN/m^2", "kPa", 1.0),
]


@pytest.mark.parametrize("expression,unit,expected", EXACT)
def test_defined_conversions_are_exact(expression, unit, expected):
    workspace = sheet(f"x = {expression}")
    assert value(workspace, "x", unit) == pytest.approx(expected, rel=1e-12)


DERIVED = [
    ("1 kip", "kN", 4.4482216152605),        # 1000 lbf, lbf = lb x g0
    ("1 lbf", "N", 4.4482216152605),
    ("1 ksi", "MPa", 6.894757293168361),
    ("1 psi", "kPa", 6.894757293168361),
    ("1 psf", "Pa", 47.88025898033584),
    ("1 kip*ft", "kN*m", 1.3558179483314006),
    ("1 g0", "m/s^2", 9.80665),
]


@pytest.mark.parametrize("expression,unit,expected", DERIVED)
def test_derived_imperial_conversions(expression, unit, expected):
    workspace = sheet(f"x = {expression}")
    assert value(workspace, "x", unit) == pytest.approx(expected, rel=1e-10)


# ---------------------------------------------------------------------------
# statics — answers anybody can reproduce by hand
# ---------------------------------------------------------------------------

def test_simply_supported_beam_under_a_udl():
    """M = wL²/8, V = wL/2, delta = 5wL⁴/384EI — the first thing you learn."""
    workspace = sheet("""
        w = 12 kN/m
        L = 6 m
        E = 210 GPa
        I = 33300 cm^4
        M_max = w*L^2/8
        V_max = w*L/2
        delta = 5*w*L^4/(384*E*I)
    """)
    assert value(workspace, "M_max", "kN*m") == pytest.approx(54.0)
    assert value(workspace, "V_max", "kN") == pytest.approx(36.0)
    # 5 x 12000 x 6^4 / (384 x 210e9 x 333e-6) m
    expected = 5 * 12000 * 6 ** 4 / (384 * 210e9 * 33300e-8)
    assert value(workspace, "delta", "m") == pytest.approx(expected, rel=1e-9)


def test_cantilever_with_a_point_load_at_the_tip():
    workspace = sheet("""
        P = 25 kN
        L = 3 m
        E = 200 GPa
        I = 8500 cm^4
        M = P*L
        delta = P*L^3/(3*E*I)
    """)
    assert value(workspace, "M", "kN*m") == pytest.approx(75.0)
    assert value(workspace, "delta", "mm") == pytest.approx(
        25e3 * 27 / (3 * 200e9 * 8500e-8) * 1000, rel=1e-9)


def test_euler_buckling_of_a_pinned_strut():
    """P_cr = pi²EI/L², the classical result."""
    workspace = sheet("""
        E = 210 GPa
        I = 1000 cm^4
        L = 4 m
        P_cr = pi^2*E*I/L^2
    """)
    expected = math.pi ** 2 * 210e9 * 1000e-8 / 16          # newtons
    assert value(workspace, "P_cr", "N") == pytest.approx(expected, rel=1e-12)


def test_a_reaction_from_moments_about_a_support():
    workspace = sheet("""
        P = 40 kN
        a = 2 m
        L = 5 m
        R_B = P*a/L
        R_A = P - R_B
    """)
    assert value(workspace, "R_B", "kN") == pytest.approx(16.0)
    assert value(workspace, "R_A", "kN") == pytest.approx(24.0)


# ---------------------------------------------------------------------------
# section properties
# ---------------------------------------------------------------------------

def test_rectangular_section_properties():
    workspace = sheet("""
        b = 300 mm
        h = 500 mm
        A = b*h
        I = b*h^3/12
        Z = b*h^2/6
        S = b*h^2/4
    """)
    assert value(workspace, "A", "mm^2") == pytest.approx(150e3)
    assert value(workspace, "I", "mm^4") == pytest.approx(300 * 500 ** 3 / 12)
    assert value(workspace, "Z", "mm^3") == pytest.approx(300 * 500 ** 2 / 6)
    assert value(workspace, "S", "mm^3") == pytest.approx(300 * 500 ** 2 / 4)


def test_area_of_a_bar_group():
    """4 no. H20 = 1257 mm², the number off every bar-area table."""
    workspace = sheet("""
        D = 20 mm
        n = 4
        A_s = n*pi*D^2/4
    """)
    assert value(workspace, "A_s", "mm^2") == pytest.approx(1256.6, rel=1e-4)


# ---------------------------------------------------------------------------
# Eurocode
# ---------------------------------------------------------------------------

def test_ec3_bending_resistance_of_a_universal_beam():
    """M_c,Rd = W_pl f_y / gamma_M0.

    457x191x67 UB in S275: W_pl,y = 1470 cm³ gives 404 kNm, the figure in the
    blue book.
    """
    workspace = sheet("""
        W_pl = 1470 cm^3
        f_y = 275 MPa
        gamma_M0 = 1.0
        M_cRd = W_pl*f_y/gamma_M0
    """)
    assert value(workspace, "M_cRd", "kN*m") == pytest.approx(404.25, rel=1e-4)


def test_ec3_shear_resistance():
    """V_pl,Rd = A_v f_y / (sqrt(3) gamma_M0)."""
    workspace = sheet("""
        A_v = 4095 mm^2
        f_y = 275 MPa
        V_plRd = A_v*f_y/(sqrt(3)*1.0)
    """)
    assert value(workspace, "V_plRd", "kN") == pytest.approx(
        4095 * 275 / math.sqrt(3) / 1000, rel=1e-9)


def test_ec2_secant_modulus_of_concrete():
    """E_cm = 22 (f_cm/10)^0.3 GPa — EN 1992-1-1 Table 3.1.

    C30/37 is tabulated at 33 GPa (the formula gives 32.8).
    """
    workspace = sheet("""
        f_ck = 30 MPa
        f_cm = f_ck + 8 MPa
        E_cm = 22*(f_cm/(10 MPa))^0.3 GPa
    """)
    assert value(workspace, "E_cm", "GPa") == pytest.approx(32.837, rel=1e-3)


def test_ec2_singly_reinforced_section():
    """K, z and A_s for a rectangular section in bending."""
    workspace = sheet("""
        M_Ed = 250 kN*m
        b = 300 mm
        d = 450 mm
        f_ck = 30 MPa
        f_yk = 500 MPa
        K = M_Ed/(b*d^2*f_ck)
        z = d*min(0.5+sqrt(0.25-K/1.134), 0.95)
        A_s = M_Ed/(0.87*f_yk*z)
    """)
    assert value(workspace, "K", "dimensionless") == pytest.approx(0.1372, rel=1e-3)
    assert value(workspace, "z", "mm") == pytest.approx(386.6, rel=1e-3)
    assert value(workspace, "A_s", "mm^2") == pytest.approx(1486, rel=1e-3)


def test_ec1_load_combination_at_ultimate_limit_state():
    """1.35 G_k + 1.5 Q_k, expression 6.10."""
    workspace = sheet("""
        gamma_conc = 25 kN/m^3
        h_slab = 200 mm
        g_slab = gamma_conc*h_slab
        g_finishes = 1.5 kPa
        G_k = g_slab + g_finishes
        Q_k = 2.5 kPa
        w_Ed = 1.35*G_k + 1.5*Q_k
    """)
    assert value(workspace, "G_k", "kPa") == pytest.approx(6.5)
    assert value(workspace, "w_Ed", "kPa") == pytest.approx(1.35 * 6.5 + 1.5 * 2.5)


def test_ec1_wind_velocity_pressure():
    """q_b = rho v²/2, with rho = 1.25 kg/m³.

    The point of this one is the unit tracking: kg/m³ times m²/s² is a
    pressure, and nothing in the sheet says so.
    """
    workspace = sheet("""
        rho_air = 1.25 kg/m^3
        v_b = 24 m/s
        q_b = 0.5*rho_air*v_b^2
    """)
    assert value(workspace, "q_b", "Pa") == pytest.approx(360.0)
    assert value(workspace, "q_b", "kN/m^2") == pytest.approx(0.36)


# ---------------------------------------------------------------------------
# American practice
# ---------------------------------------------------------------------------

def test_aisc_flexural_design_strength():
    """phi M_n = 0.9 F_y Z_x.

    W18x50 in Grade 50: Z_x = 101 in³ gives 379 kip-ft in the steel manual.
    """
    workspace = sheet("""
        Z_x = 101 in^3
        F_y = 50 ksi
        phi_b = 0.9
        M_n = phi_b*F_y*Z_x
    """)
    assert value(workspace, "M_n", "kip*ft") == pytest.approx(378.75, rel=1e-4)
    assert value(workspace, "M_n", "kN*m") == pytest.approx(513.5, rel=1e-3)


def test_aci_concrete_modulus():
    """E_c = 57000 sqrt(f'_c) psi, with f'_c in psi — ACI 318."""
    workspace = sheet("""
        f_c = 4000 psi
        E_c = 57000*sqrt(f_c/(1 psi)) psi
    """)
    assert value(workspace, "E_c", "ksi") == pytest.approx(
        57000 * math.sqrt(4000) / 1000, rel=1e-6)
    assert value(workspace, "E_c", "GPa") == pytest.approx(24.87, rel=1e-3)


def test_mixing_imperial_and_metric_in_one_sheet():
    """The whole point of unit tracking: the sheet does not care."""
    workspace = sheet("""
        P = 10 kip
        A = 5000 mm^2
        sigma = P/A
    """)
    assert value(workspace, "sigma", "MPa") == pytest.approx(
        10 * 4448.2216152605 / 5000, rel=1e-9)
    assert value(workspace, "sigma", "ksi") == pytest.approx(1.29, rel=1e-2)


# ---------------------------------------------------------------------------
# geotechnics and hydraulics
# ---------------------------------------------------------------------------

def test_effective_stress_in_a_soil_profile():
    workspace = sheet("""
        gamma_sat = 20 kN/m^3
        gamma_w = 9.81 kN/m^3
        z = 6 m
        z_w = 4 m
        sigma_v = gamma_sat*z
        u = gamma_w*z_w
        sigma_eff = sigma_v - u
    """)
    assert value(workspace, "sigma_v", "kPa") == pytest.approx(120.0)
    assert value(workspace, "u", "kPa") == pytest.approx(39.24)
    assert value(workspace, "sigma_eff", "kPa") == pytest.approx(80.76)


def test_rankine_active_pressure_coefficient():
    """K_a = (1 - sin phi)/(1 + sin phi); 30 deg gives exactly 1/3."""
    workspace = sheet("""
        phi_soil = 30 deg
        K_a = (1-sin(phi_soil))/(1+sin(phi_soil))
        gamma_soil = 18 kN/m^3
        H = 4 m
        P_a = 0.5*K_a*gamma_soil*H^2
    """)
    assert value(workspace, "K_a", "dimensionless") == pytest.approx(1 / 3, rel=1e-9)
    assert value(workspace, "P_a", "kN/m") == pytest.approx(48.0, rel=1e-6)


def test_pad_footing_bearing_pressure_with_eccentricity():
    workspace = sheet("""
        N = 1500 kN
        B = 2.5 m
        L = 2.5 m
        e = 0.2 m
        q_avg = N/(B*L)
        q_max = N/(B*L)*(1+6*e/B)
        q_min = N/(B*L)*(1-6*e/B)
    """)
    assert value(workspace, "q_avg", "kPa") == pytest.approx(240.0)
    assert value(workspace, "q_max", "kPa") == pytest.approx(355.2)
    assert value(workspace, "q_min", "kPa") == pytest.approx(124.8)


def test_flow_in_a_pipe():
    """Q = A v, and the units have to come out as litres per second."""
    workspace = sheet("""
        D = 150 mm
        v = 1.2 m/s
        A = pi*D^2/4
        Q = A*v
    """)
    expected = math.pi * 0.15 ** 2 / 4 * 1.2 * 1000        # litres per second
    assert value(workspace, "Q", "l/s") == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# thermal
# ---------------------------------------------------------------------------

def test_thermal_expansion_of_a_steel_member():
    workspace = sheet("""
        alpha = 12e-6/K
        dT = 35 K
        L = 30 m
        dL = alpha*dT*L
    """)
    assert value(workspace, "dL", "mm") == pytest.approx(12.6, rel=1e-9)


def test_temperatures_convert_across_their_offsets():
    workspace = sheet("""
        T_c = 20 degC
        T_k = T_c -> K
    """)
    assert value(workspace, "T_c", "degC") == pytest.approx(20.0)
    assert value(workspace, "T_k", "K") == pytest.approx(293.15)


# ---------------------------------------------------------------------------
# a full sheet, the way it would really be written
# ---------------------------------------------------------------------------

def test_a_complete_beam_design_sheet():
    """Load take-down, analysis and a capacity check in one page."""
    workspace = sheet("""
        # loading
        gamma_conc = 25 kN/m^3
        h_slab = 175 mm
        g_slab = gamma_conc*h_slab
        g_finishes = 1.2 kPa
        g_services = 0.5 kPa
        G_k = g_slab + g_finishes + g_services
        Q_k = 3.0 kPa

        # geometry
        b_trib = 4.2 m
        L = 7.5 m

        # design load
        w_Ed = (1.35*G_k + 1.5*Q_k)*b_trib
        M_Ed = w_Ed*L^2/8
        V_Ed = w_Ed*L/2

        # section
        W_pl = 1500 cm^3
        f_y = 355 MPa
        M_cRd = W_pl*f_y/1.0
        utilisation = M_Ed/M_cRd
    """)
    g_k = 25 * 0.175 + 1.2 + 0.5                       # 6.075 kPa
    w = (1.35 * g_k + 1.5 * 3.0) * 4.2                 # kN/m
    assert value(workspace, "G_k", "kPa") == pytest.approx(g_k)
    assert value(workspace, "w_Ed", "kN/m") == pytest.approx(w)
    assert value(workspace, "M_Ed", "kN*m") == pytest.approx(w * 7.5 ** 2 / 8)
    assert value(workspace, "V_Ed", "kN") == pytest.approx(w * 7.5 / 2)
    assert value(workspace, "M_cRd", "kN*m") == pytest.approx(532.5)
    assert value(workspace, "utilisation", "dimensionless") == pytest.approx(
        w * 7.5 ** 2 / 8 / 532.5, rel=1e-9)
