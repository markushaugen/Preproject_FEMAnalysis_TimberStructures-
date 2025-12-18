# ec5/connection.py

from dataclasses import dataclass
from typing import Dict
import math

from .design_values import TimberDesign, LoadDuration, GAMMA_M_CONN


@dataclass
class FastenerSetup:
    d_mm: float       
    t_wood_mm: float  
    n: int            
    fy_steel: float = 355e6  


def embedment_strength_char(rho_k: float, d_mm: float) -> float:
    """
    Characteristic embedment strength fh,0,k [N/mm^2] for bolts/dowels
    according to an EC5-style expression:
        fh,0,k = 0.082 * (1 - 0.01 * d) * rho_k
    with rho_k in kg/m^3 and d in mm.
    Returns fh,0,k in N/mm^2.
    """
    return 0.082 * (1.0 - 0.01 * d_mm) * rho_k  


def bolt_yield_moment_char(d_mm: float, fy: float) -> float:
    """
    Characteristic plastic bending moment of the fastener, My,Rk [Nmm].
    Common expression:
        My,Rk = 0.3 * fy * d^3
    with fy in N/mm^2 and d in mm.
    """
    fy_N_per_mm2 = fy / 1e6  
    return 0.3 * fy_N_per_mm2 * (d_mm ** 3)  


def eym_single_shear_design(
    timber: TimberDesign,
    duration: LoadDuration,
    setup: FastenerSetup,
    rho_k: float,
    gamma_M_conn: float = GAMMA_M_CONN,
) -> Dict[str, float]:
    """
    Johansen-type single-shear, steel-to-timber with slotted-in plate (thick steel).
    Modes considered per fastener:
      a) Timber bearing (embedment controlled)
      b) One plastic hinge in the fastener
      c) Two plastic hinges in the fastener

    Rk formulas (per fastener, in N):
      Rk_a = fhk * d * t
      Rk_b = 1.15 * sqrt( 2 * My_Rk * fhk * d )
      Rk_c = 2.3 * My_Rk / t

    Design resistance:
      Rd = k_mod * Rk / gamma_M_conn
    """
    d = setup.d_mm
    t = setup.t_wood_mm
    n = setup.n

    # Characteristic embedment strength fh,k 
    fhk = embedment_strength_char(rho_k, d)

    # Characteristic fastener yield moment My,Rk 
    My_Rk = bolt_yield_moment_char(d, setup.fy_steel)

    # Characteristic per-fastener resistances 
    Rk_a = fhk * d * t
    Rk_b = 1.15 * math.sqrt(2.0 * My_Rk * fhk * d)
    Rk_c = 2.3 * My_Rk / t

    kmod = timber.k_mod(duration)

    # Design values 
    Rd_a = kmod * Rk_a / gamma_M_conn
    Rd_b = kmod * Rk_b / gamma_M_conn
    Rd_c = kmod * Rk_c / gamma_M_conn

    per_fastener = min(Rd_a, Rd_b, Rd_c)

    return {
        "Rd_mode_a_N": Rd_a,
        "Rd_mode_b_N": Rd_b,
        "Rd_mode_c_N": Rd_c,
        "Rd_governing_per_fastener_N": per_fastener,
        "Rd_total_N": per_fastener * n,
        "modes_sorted_N": sorted(
            [("a", Rd_a), ("b", Rd_b), ("c", Rd_c)],
            key=lambda x: x[1],
        ),
    }
