# ec5/connection.py
# Explanations in English.

from dataclasses import dataclass
from typing import Dict
import math
from .design_values import TimberDesign, LoadDuration, GAMMA_M_CONN

@dataclass
class FastenerSetup:
    d_mm: float      # dowel/bolt diameter [mm]
    t_wood_mm: float # timber thickness engaged in one shear plane [mm]
    n: int           # number of fasteners (single shear, single row for now)
    fy_steel: float = 355e6  # bolt steel yield strength [Pa] (typical S355)

def embedment_strength_char(rho_k: float, d_mm: float) -> float:
    """
    EC5-style embedment strength fh,0,k [Pa] for bolts/dowels:
    fh,0,k = 0.082 * (1 - 0.01*d) * rho_k  [N/mm^2]  -> convert to Pa
    rho_k in kg/m3, d in mm.
    """
    fh_N_per_mm2 = 0.082 * (1.0 - 0.01 * d_mm) * rho_k  # N/mm^2 = MPa
    return fh_N_per_mm2 * 1e6  # Pa

def bolt_yield_moment_char(d_mm: float, fy: float) -> float:
    """
    Characteristic plastic bending moment of fastener, My,Rk [N*mm].
    Common expression used with EC5/Johansen-type checks:
      My,Rk = 0.3 * fy * d^3   (fy in N/mm^2)
    Here fy is in Pa -> convert to N/mm^2 first.
    """
    fy_N_per_mm2 = fy / 1e6
    return 0.3 * fy_N_per_mm2 * (d_mm ** 3)  # N*mm

def eym_single_shear_design(
    timber: TimberDesign,
    duration: LoadDuration,
    setup: FastenerSetup,
    rho_k: float,
    gamma_M_conn: float = GAMMA_M_CONN,
) -> Dict[str, float]:
    """
    EC5/Johansen single-shear, steel-to-timber with slotted-in plate (thick steel) — schematic but useful.
    Modes considered (per fastener):
      a) Timber bearing (embedment) controlled
      b) One plastic hinge in the fastener
      c) Two plastic hinges in the fastener
    Rk formulas (commonly used closed-forms):
      Rk_a = fhk * d * t
      Rk_b = 1.15 * sqrt( 2 * My_Rk * fhk * d )
      Rk_c = 2.3 * My_Rk / t
    Design: Rd = k_mod * Rk / gamma_M_conn
    Returns per-mode Rd [N], governing per-fastener Rd, and total Rd for n fasteners.
    """
    d = setup.d_mm
    t = setup.t_wood_mm
    n = setup.n

    fhk = embedment_strength_char(rho_k, d)              # Pa
    # Convert fhk [Pa] acting on projected area [mm^2] -> be consistent:
    # We'll compute Rk in Newton by converting area d* t [mm^2] to m^2.
    area_m2 = (d * t) * 1e-6
    Rk_a = fhk * area_m2  # N

    My_Rk = bolt_yield_moment_char(d, setup.fy_steel)    # N*mm
    # Rk_b uses sqrt(2 * My * fhk * d). Keep units consistent:
    # fhk [Pa] * d [mm] -> convert d to meters inside fhk*d product: fhk * (d*1e-3) [N/m^2 * m] = N/m
    # Multiply by My [N*mm] -> convert mm to m: My [N*m]
    # => inside sqrt we form N*m * N/m = N^2 -> sqrt -> N
    Rk_b = 1.15 * math.sqrt(2.0 * (My_Rk * 1e-3) * (fhk * (d * 1e-3)))  # N

    # Rk_c = 2.3 * My / t ; My in N*mm, t in mm -> N
    Rk_c = 2.3 * My_Rk / t  # N

    # Design values with k_mod and gamma_M_conn
    Rd_a = timber.design_value(Rk_a, duration, gamma_M_conn)  # N
    Rd_b = timber.design_value(Rk_b, duration, gamma_M_conn)  # N
    Rd_c = timber.design_value(Rk_c, duration, gamma_M_conn)  # N

    per_fastener = min(max(Rd_a, 0.0), max(Rd_b, 0.0), max(Rd_c, 0.0))  # conservative choose min of the three modes?
    # For governing capacity per fastener, take the minimum (weakest) mode:
    per_fastener = min(Rd_a, Rd_b, Rd_c)

    return {
        "Rd_mode_a_N": Rd_a,
        "Rd_mode_b_N": Rd_b,
        "Rd_mode_c_N": Rd_c,
        "Rd_governing_per_fastener_N": per_fastener,
        "Rd_total_N": per_fastener * n,
        "modes_sorted_N": sorted([("a", Rd_a), ("b", Rd_b), ("c", Rd_c)], key=lambda x: x[1]),
    }
