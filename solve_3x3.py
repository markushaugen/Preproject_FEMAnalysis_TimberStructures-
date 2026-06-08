"""
Full nonlinear solve for the 3-row x 3-column dowel configuration.
L=1000, H=240, B=140 mm — dowels at x=[660,780,900], y=[60,120,180].
d=12 mm, GL30h timber (mat=1) / S355 steel plate (mat=2).

EC5 Johansen characteristic resistance (double shear, Mode c governing):
  fh,k = 36.1 N/mm²,  Myrk ≈ 153 500 N·mm,  t1 = 70 mm
  Fv,Rk,c ≈ 31.2 kN/dowel
  Group effect nef = 3^0.9 ≈ 2.69 per row (3 cols in load direction, a1=10d)
  Total: 3 rows × 2.69 × 31.2 kN ≈ 252 kN  (characteristic, not design value)
"""

import os
import time
import subprocess
import sys

# ── Parameters ────────────────────────────────────────────────────────────────
L            = 1000
H            = 240
B            = 140
t_plate      = 8
n_rows       = 3
n_cols       = 3
s_dowel      = 120   # column spacing [mm]
a_edge       = 100   # end edge to first (rightmost) column [mm]
row_spacing  = 60    # row spacing [mm]
d_dowel      = 12    # nominal diameter [mm]
clearance    = 0.5
mesh_size    = 40    # global element size [mm]; keeps nodes below 32k limit
imposed_disp = 20.0
F_ec5_kN     = 252.0   # EC5 Johansen characteristic (see docstring)

# GL30h characteristic strengths [MPa]
fvk  = 3.5    # shear
ft0k = 24.0   # tension parallel to grain

# ── Import model functions ────────────────────────────────────────────────────
from pymapdl_model import (
    build_model, add_contacts, add_bcs_and_solve,
    verify_force_transfer,
    _print_contact_pairs, _print_dowel_displacements,
)

OUT_DIR = "out_3x3"


def _clear_lock():
    lockfile = os.path.join(OUT_DIR, "file.lock")
    if os.path.exists(lockfile):
        try:
            os.remove(lockfile)
        except PermissionError:
            subprocess.call(
                ["taskkill", "/F", "/IM", "ANSYS.exe", "/T"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(3)
            try:
                os.remove(lockfile)
            except OSError:
                pass


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    _clear_lock()

    print("=" * 65)
    print(f"  3x3 dowel configuration  —  full nonlinear solve")
    print(f"  Output directory: {OUT_DIR}/")
    print(f"  L={L}  H={H}  B={B}  t_plate={t_plate}")
    print(f"  d_dowel={d_dowel}  mesh_size={mesh_size}")
    print(f"  imposed_disp={imposed_disp} mm")
    print(f"  EC5 Johansen characteristic ≈ {F_ec5_kN} kN")
    print("=" * 65)

    mapdl, vid_beam, vid_plate, vid_dowels, positions, sz1, sz2 = build_model(
        L=L, H=H, B=B, t_plate=t_plate,
        n_rows=n_rows, n_cols=n_cols,
        s_dowel=s_dowel, a_edge=a_edge, row_spacing=row_spacing,
        d_dowel=d_dowel, mesh_size=mesh_size,
        block_shear=False, clearance=clearance,
        run_location=OUT_DIR,
    )

    n_dowels = len(vid_dowels)
    n_pairs  = n_dowels * 2

    try:
        add_contacts(
            mapdl, positions, vid_beam, vid_plate, vid_dowels,
            sz1=sz1, sz2=sz2,
            mu_timber=0.3, mu_plate=0.15, pinb=10,
        )

        mapdl.save("pymapdl_3x3_presolve", "db")

        vr = verify_force_transfer(
            mapdl, L=L, H=H, B=B, t_plate=t_plate,
            positions=positions,
            ux_verify=2.0, nsubst=(20, 100, 5),
        )

        if abs(vr["fx_reaction"]) < 10.0:
            print("\nVerification FAILED — no reaction force at x=0 (contact inactive).")
            sys.exit(1)

        print("\nResuming presolve DB to restore undeformed mesh...")
        mapdl.finish()
        mapdl.resume("pymapdl_3x3_presolve", "db")
        print("Resume complete — starting full nonlinear solve.")

        add_bcs_and_solve(
            mapdl, L=L, H=H, B=B, t_plate=t_plate,
            imposed_disp=imposed_disp,
            nsubst=(20, 200, 5),
        )

        mapdl.save("pymapdl_3x3_solved", "db")

        _postprocess_3x3(
            mapdl,
            positions=positions,
            imposed_disp=imposed_disp,
            F_ec5_kN=F_ec5_kN,
            n_pairs=n_pairs,
        )

    finally:
        try:
            mapdl.exit()
        except Exception:
            pass
        lock = os.path.join(OUT_DIR, "file.lock")
        for _ in range(20):
            if not os.path.exists(lock):
                break
            time.sleep(1)


def _global_timber_stress_max(mapdl):
    def _get(name):
        try:
            return float(mapdl.parameters[name])
        except (KeyError, TypeError, ValueError):
            return 0.0

    mapdl.allsel()
    mapdl.esel("s", "mat", "", 1)
    mapdl.run("ETABLE,PCSY, S,Y")
    mapdl.run("ETABLE,PCSXY,S,XY")
    mapdl.run("*GET,PCSMX1,ETAB,EXTR,PCSY, MAX")
    mapdl.run("*GET,PCSMN1,ETAB,EXTR,PCSY, MIN")
    mapdl.run("*GET,PCSMX2,ETAB,EXTR,PCSXY,MAX")
    mapdl.run("*GET,PCSMN2,ETAB,EXTR,PCSXY,MIN")
    sy  = max(abs(_get("PCSMX1")), abs(_get("PCSMN1")))
    sxy = max(abs(_get("PCSMX2")), abs(_get("PCSMN2")))
    mapdl.allsel()
    return sy, sxy


def _postprocess_3x3(mapdl, positions, imposed_disp, F_ec5_kN, n_pairs):
    import csv
    import matplotlib.pyplot as plt

    r_hole      = d_dowel / 2 + clearance
    y_shear_bot = min(y for _, y in positions) - r_hole   # ≈ 53.5 mm
    y_shear_top = max(y for _, y in positions) + r_hole   # ≈ 186.5 mm
    x_tension   = min(x for x, _ in positions) - r_hole   # ≈ 653.5 mm
    eps         = 10.0

    print(f"\nBlock-shear failure planes:")
    print(f"  Shear bottom : y = {y_shear_bot:.1f} mm")
    print(f"  Shear top    : y = {y_shear_top:.1f} mm")
    print(f"  Tension      : x = {x_tension:.1f} mm")

    mapdl.run("/POST1")
    mapdl.run("INRES,ALL")
    times = mapdl.post_processing.time_values
    print(f"Result sets: {len(times)}")

    if len(times) >= 2 and times[-1] >= 0.999 and times[-2] < 0.99:
        times = times[:-1]
        print(f"  (dropped spurious end-time entry; using {len(times)} result sets)")

    forces_kN    = []
    disps_mm     = []
    fi_shear_bot = []
    fi_shear_top = []
    fi_tension   = []

    def _plane_stress_max(axis, val, xlo, xhi, ylo, yhi, comp):
        mapdl.allsel()
        mapdl.esel("s", "type", "", 1)
        if axis == "y":
            mapdl.nsel("s", "loc", "y", val - eps, val + eps)
        else:
            mapdl.nsel("s", "loc", "x", val - eps, val + eps)
        mapdl.nsel("r", "loc", "x", xlo, xhi)
        mapdl.nsel("r", "loc", "y", ylo, yhi)
        mapdl.run("ESLN,S,0")
        if mapdl.mesh.n_elem == 0:
            return 0.0
        lbl = "STMP"
        mapdl.run(f"ETABLE,{lbl},S,{comp}")
        mapdl.run(f"*GET,SMXP,ETAB,EXTR,{lbl},MAX")
        mapdl.run(f"*GET,SMNP,ETAB,EXTR,{lbl},MIN")
        try:
            vmax = float(mapdl.parameters["SMXP"])
        except (KeyError, TypeError, ValueError):
            vmax = 0.0
        try:
            vmin = float(mapdl.parameters["SMNP"])
        except (KeyError, TypeError, ValueError):
            vmin = 0.0
        return max(abs(vmax), abs(vmin))

    mapdl.run("SET,FIRST")
    _prev = mapdl.ignore_errors
    mapdl.ignore_errors = True

    for t in times:
        mapdl.allsel()
        mapdl.nsel("s", "loc", "x", -0.1, 0.1)
        mapdl.run("NFORCE,ALL")
        mapdl.run("FSUM")
        mapdl.run("*GET,PFFX,FSUM,,ITEM,FX")
        try:
            fx = float(mapdl.parameters["PFFX"])
        except (KeyError, TypeError, ValueError):
            fx = 0.0
        forces_kN.append(abs(fx) / 1000.0)
        disps_mm.append(t * imposed_disp)

        sxy_bot = _plane_stress_max("y", y_shear_bot,
                                    x_tension, L, -1, y_shear_bot + eps + 1, "XY")
        fi_shear_bot.append(sxy_bot / fvk)

        sxy_top = _plane_stress_max("y", y_shear_top,
                                    x_tension, L, y_shear_top - eps - 1, H + 1, "XY")
        fi_shear_top.append(sxy_top / fvk)

        sx_ten = _plane_stress_max("x", x_tension,
                                   -1, x_tension + eps + 1, y_shear_bot, y_shear_top, "X")
        fi_tension.append(max(0.0, sx_ten) / ft0k)

        mapdl.allsel()
        mapdl.run("SET,NEXT")

    mapdl.ignore_errors = _prev

    peak_idx = forces_kN.index(max(forces_kN)) if forces_kN else 0
    mapdl.run("SET,FIRST")
    for _ in range(peak_idx):
        mapdl.run("SET,NEXT")
    sy_max, sxy_max = _global_timber_stress_max(mapdl)
    print(f"\nPeak-load global timber stresses:")
    print(f"  Sy  max : {sy_max:.3f} MPa   (ft,90,k = 0.50 MPa → ratio {sy_max/0.50:.2f})")
    print(f"  Sxy max : {sxy_max:.3f} MPa  (fv,k    = 3.50 MPa → ratio {sxy_max/3.50:.2f})")

    fi_max = [max(b, t, n) for b, t, n in zip(fi_shear_bot, fi_shear_top, fi_tension)]
    fail_idx   = next((i for i, fi in enumerate(fi_max) if fi >= 1.0), None)
    fail_disp  = disps_mm[fail_idx]   if fail_idx is not None else None
    fail_force = forces_kN[fail_idx]  if fail_idx is not None else None

    if fail_idx is not None:
        fb = fi_shear_bot[fail_idx]
        ft = fi_shear_top[fail_idx]
        fn = fi_tension[fail_idx]
        gov = ["shear-bot", "shear-top", "tension"][[fb, ft, fn].index(max(fb, ft, fn))]
        print(f"\nFirst failure at disp = {fail_disp:.2f} mm,  F = {fail_force:.1f} kN")
        print(f"  Governing plane : {gov}")
        print(f"  FI shear-bot={fb:.3f}  shear-top={ft:.3f}  tension={fn:.3f}")
    else:
        print("\nNo failure criterion exceeded within the applied displacement.")

    peak_f = max(forces_kN) if forces_kN else 0.0
    peak_d = disps_mm[forces_kN.index(peak_f)] if forces_kN else 0.0

    csv_path = os.path.join(OUT_DIR, "force_displacement_3x3.csv")
    try:
        os.remove(csv_path)
    except OSError:
        pass
    with open(csv_path, "w", newline="") as f:
        import csv as _csv
        w = _csv.writer(f)
        w.writerow(["displacement_mm", "force_kN",
                    "fi_shear_bot", "fi_shear_top", "fi_tension"])
        w.writerows(zip(disps_mm, forces_kN, fi_shear_bot, fi_shear_top, fi_tension))
    print(f"Saved {csv_path}")

    # Load last well-converged substep for contact/dowel summaries
    mapdl.run("INRES,ALL")
    mapdl.run("SET,LAST")
    mapdl.run("SET,PREV")

    try:
        _print_contact_pairs(mapdl, n_pairs)
    except Exception as e:
        print(f"WARNING: contact pair summary failed: {e}")
    try:
        _print_dowel_displacements(mapdl, positions)
    except Exception as e:
        print(f"WARNING: dowel displacement summary failed: {e}")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 9),
                                   gridspec_kw={"height_ratios": [3, 1]})

    ax1.plot(disps_mm, forces_kN, "b-o", markersize=3,
             label="FEM (3×3 dowels, d=12 mm, GL30h)")
    ax1.axhline(F_ec5_kN, color="r", linestyle="--", linewidth=1.5,
                label=f"EC5 Johansen Rk ≈ {F_ec5_kN:.0f} kN")

    if fail_idx is not None:
        ax1.axvline(fail_disp, color="darkorange", linestyle=":", linewidth=1.5,
                    label=f"Failure initiation ({gov})  {fail_force:.0f} kN @ {fail_disp:.1f} mm")
        ax1.plot(fail_disp, fail_force, "o", color="darkorange", markersize=8, zorder=5)

    if peak_f > 0:
        ax1.annotate(f"Peak {peak_f:.1f} kN\n@ {peak_d:.1f} mm",
                     xy=(peak_d, peak_f),
                     xytext=(peak_d + 0.5, peak_f * 0.88),
                     arrowprops=dict(arrowstyle="->", color="navy"),
                     color="navy", fontsize=9)

    ax1.set_ylabel("Force [kN]", fontsize=11)
    ax1.set_title("Block Shear — Force–Displacement  (3r×3c, GL30h, d=12 mm)", fontsize=12)
    ax1.legend(fontsize=9)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.set_xlim(left=0)

    ax2.plot(disps_mm, fi_shear_bot, "g-",  linewidth=1.5, label=f"Shear bot (fvk={fvk} MPa)")
    ax2.plot(disps_mm, fi_shear_top, "g--", linewidth=1.5, label="Shear top")
    ax2.plot(disps_mm, fi_tension,   "m-",  linewidth=1.5, label=f"Tension (ft0k={ft0k} MPa)")
    ax2.axhline(1.0, color="r", linestyle="--", linewidth=1.0, label="FI = 1.0 (failure)")
    if fail_idx is not None:
        ax2.axvline(fail_disp, color="darkorange", linestyle=":", linewidth=1.5)

    ax2.set_xlabel("Displacement [mm]", fontsize=11)
    ax2.set_ylabel("Failure Index  [-]", fontsize=11)
    ax2.legend(fontsize=9, loc="upper left")
    ax2.grid(True, linestyle="--", alpha=0.5)
    ax2.set_xlim(left=0)
    ax2.set_ylim(bottom=0)

    plt.tight_layout()
    out_png = os.path.join(OUT_DIR, "force_displacement_3x3.png")
    plt.savefig(out_png, dpi=150)
    print(f"Saved {out_png}")
    plt.show()

    print(f"\nPeak FEM force : {peak_f:.1f} kN  at  {peak_d:.1f} mm displacement")
    print(f"EC5 Johansen Rk: {F_ec5_kN:.1f} kN")
    if peak_f > 0:
        ratio = peak_f / F_ec5_kN
        print(f"FEM/EC5 ratio  : {ratio:.3f}  ({'above' if ratio >= 1 else 'below'} EC5)")
    if fail_force is not None:
        print(f"Fail/EC5 ratio : {fail_force/F_ec5_kN:.3f}  (first failure vs reference)")


if __name__ == "__main__":
    main()
