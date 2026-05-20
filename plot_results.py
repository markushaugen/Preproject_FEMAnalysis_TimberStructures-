#!/usr/bin/env python3
"""
Plot FEM force-displacement curve with EC5 block shear capacity overlay.

Usage:
    python plot_results.py [--csv PATH] [--params PATH] [--ec5-only]
"""

import argparse
import csv
import json
import os
import sys


def parse_args():
    p = argparse.ArgumentParser(description="Plot FEM F-d curve vs EC5 block shear")
    p.add_argument("--csv", default="force_displacement.csv",
                   help="Path to ANSYS force_displacement.csv (default: force_displacement.csv)")
    p.add_argument("--params", default="out/model_params.json",
                   help="Path to model_params.json (default: out/model_params.json)")
    p.add_argument("--ec5-only", action="store_true",
                   help="Compute and print EC5 capacity without plotting")
    return p.parse_args()


def load_params(path):
    with open(path) as f:
        return json.load(f)


def ec5_block_shear(params):
    """
    EC5 Annex A block shear (EN 1995-1-1:2004, eq. A.1).
    F_bs,Rk = max(1.5 * A_net,t * ft0k,  0.7 * A_net,v * fvk)
    """
    geo = params["geometry_mm"]

    # GL30h characteristic values (EN 14080), MPa = N/mm²
    ft0k = 24.0
    fvk  = 3.5

    B         = geo["B"]
    H         = geo["H"]
    n_rows    = geo["n_rows"]
    n_cols    = geo["n_cols"]
    d_dowel   = geo["d_dowel"]
    s_dowel   = geo["s_dowel"]
    a_edge    = geo["a_edge"]
    n_plates  = geo.get("n_plates", 1)
    positions = geo["dowel_positions"]

    # Infer row spacing from dowel Y-coordinates
    ys = sorted(set(round(y, 1) for _, y in positions))
    row_spacing = (ys[-1] - ys[0]) / (n_rows - 1) if n_rows > 1 else 0.0

    tef            = B                       # effective thickness: full beam width (double shear)
    n_shear_planes = 2 * n_plates            # 2 shear planes per slotted plate
    d_hole         = d_dowel + 1.0           # nominal hole diameter (mm)

    # Net shear length parallel to grain (plate end → first fastener row)
    L_netv = a_edge + (n_cols - 1) * s_dowel - n_cols * d_hole
    A_netv = n_shear_planes * L_netv * tef   # mm²

    # Net tension width perpendicular to grain
    a4t    = min(y for _, y in positions)    # min edge distance to fastener
    L_nett = H - 2 * a4t - (n_rows - 1) * (row_spacing - d_hole)
    A_nett = L_nett * tef                    # mm²

    # Characteristic block shear capacity (N)
    F_tension = 1.5 * A_nett * ft0k
    F_shear   = 0.7 * A_netv * fvk
    F_bs_Rk   = max(F_tension, F_shear)

    gamma_M  = 1.3
    F_bs_Rd  = F_bs_Rk / gamma_M

    return {
        "mat_class":          params["class"],
        "ft0k_MPa":           ft0k,
        "fvk_MPa":            fvk,
        "tef_mm":             tef,
        "n_shear_planes":     n_shear_planes,
        "d_hole_mm":          d_hole,
        "L_netv_mm":          L_netv,
        "A_netv_mm2":         A_netv,
        "a4t_mm":             a4t,
        "row_spacing_mm":     row_spacing,
        "L_nett_mm":          L_nett,
        "A_nett_mm2":         A_nett,
        "F_bs_Rk_tension_N":  F_tension,
        "F_bs_Rk_shear_N":    F_shear,
        "F_bs_Rk_N":          F_bs_Rk,
        "gamma_M":            gamma_M,
        "F_bs_Rd_N":          F_bs_Rd,
    }


def print_ec5(ec5):
    print("\n--- EC5 Annex A Block Shear (EN 1995-1-1:2004 eq. A.1) ---")
    print(f"  Material class       : {ec5['mat_class']}")
    print(f"  ft0k                 : {ec5['ft0k_MPa']:.1f} MPa")
    print(f"  fvk                  : {ec5['fvk_MPa']:.1f} MPa")
    print(f"  tef                  : {ec5['tef_mm']:.1f} mm")
    print(f"  n_shear_planes       : {ec5['n_shear_planes']}")
    print(f"  d_hole               : {ec5['d_hole_mm']:.1f} mm")
    print(f"  L_netv               : {ec5['L_netv_mm']:.1f} mm")
    print(f"  A_netv               : {ec5['A_netv_mm2']:.1f} mm²")
    print(f"  a4t (min edge dist)  : {ec5['a4t_mm']:.1f} mm")
    print(f"  row_spacing          : {ec5['row_spacing_mm']:.1f} mm")
    print(f"  L_nett               : {ec5['L_nett_mm']:.1f} mm")
    print(f"  A_nett               : {ec5['A_nett_mm2']:.1f} mm²")
    print(f"  Tension component    : {ec5['F_bs_Rk_tension_N'] / 1000:.2f} kN")
    print(f"  Shear component      : {ec5['F_bs_Rk_shear_N'] / 1000:.2f} kN")
    governing = "tension" if ec5["F_bs_Rk_tension_N"] >= ec5["F_bs_Rk_shear_N"] else "shear"
    print(f"  F_bs,Rk              : {ec5['F_bs_Rk_N'] / 1000:.2f} kN  (governs: {governing})")
    print(f"  gamma_M              : {ec5['gamma_M']:.1f}")
    print(f"  F_bs,Rd              : {ec5['F_bs_Rd_N'] / 1000:.2f} kN")
    print()


def read_csv(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        # Strip whitespace from keys (APDL *vwrite pads with spaces)
        for row in reader:
            rows.append({k.strip(): float(v) for k, v in row.items()})
    if not rows:
        print(f"ERROR: {path} is empty.")
        sys.exit(1)
    return rows


def plot(data, ec5):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        print("matplotlib not installed — run: pip install matplotlib")
        sys.exit(1)

    ux = [abs(r["UX_mm"]) for r in data]
    fx = [abs(r["FX_N"]) / 1000.0 for r in data]   # N → kN

    F_rk = ec5["F_bs_Rk_N"] / 1000.0
    F_rd = ec5["F_bs_Rd_N"] / 1000.0

    peak_idx = fx.index(max(fx))
    peak_ux  = ux[peak_idx]
    peak_fx  = fx[peak_idx]
    ratio    = peak_fx / F_rk

    fig, ax = plt.subplots(figsize=(9, 6))

    ax.plot(ux, fx, "b-o", linewidth=1.5, markersize=3, label="FEM")
    ax.axhline(F_rk, color="red",    linestyle="--", linewidth=1.5,
               label=f"EC5 $F_{{bs,Rk}}$ = {F_rk:.1f} kN")
    ax.axhline(F_rd, color="orange", linestyle=":",  linewidth=1.5,
               label=f"EC5 $F_{{bs,Rd}}$ = {F_rd:.1f} kN")

    ax.plot(peak_ux, peak_fx, "r*", markersize=12, zorder=5, label="Peak FEM")
    ax.annotate(
        f"Peak: {peak_fx:.1f} kN\n$F_{{FEM}}/F_{{bs,Rk}}$ = {ratio:.2f}",
        xy=(peak_ux, peak_fx),
        xytext=(peak_ux + max(ux) * 0.05, peak_fx * 0.92),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color="black"),
    )

    ax.set_xlabel("Displacement UX (mm)")
    ax.set_ylabel("Reaction force FX (kN)")
    ax.set_title("FEM Force–Displacement vs EC5 Block Shear Capacity")
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_minor_locator(ticker.AutoMinorLocator())
    ax.yaxis.set_minor_locator(ticker.AutoMinorLocator())

    os.makedirs("out", exist_ok=True)
    outpath = os.path.join("out", "load_displacement.png")
    fig.savefig(outpath, dpi=150, bbox_inches="tight")
    print(f"Saved plot to {outpath}")
    plt.show()


if __name__ == "__main__":
    args = parse_args()

    if not os.path.exists(args.params):
        print(f"ERROR: params file not found: {args.params}")
        sys.exit(1)

    params = load_params(args.params)
    ec5    = ec5_block_shear(params)
    print_ec5(ec5)

    if args.ec5_only:
        sys.exit(0)

    if not os.path.exists(args.csv):
        print(f"CSV not found: {args.csv}")
        print("Use --ec5-only to skip the plot, or --csv <path> to point at the ANSYS output.")
        sys.exit(1)

    data = read_csv(args.csv)
    plot(data, ec5)
