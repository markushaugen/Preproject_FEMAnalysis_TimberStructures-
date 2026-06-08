"""
Full nonlinear solve for the 2-row x 4-column dowel configuration.
H=200 mm, B=140 mm, d=12 mm, GL30h timber / S355 steel plate.
EC5 block shear reference capacity: 270.4 kN.
"""

import os
import time
import subprocess
import sys

# ── Parameters ────────────────────────────────────────────────────────────────
L            = 1000
H            = 200
B            = 140
t_plate      = 8
n_rows       = 2
n_cols       = 4
d_dowel      = 12
mesh_size    = 35       # global element size [mm]; increase if node limit exceeded
imposed_disp = 20.0    # [mm]
F_ec5_kN     = 270.4   # EC5 block shear reference capacity

# ── Import model functions ────────────────────────────────────────────────────
from pymapdl_model import (
    build_model, add_contacts, add_bcs_and_solve,
    verify_force_transfer, postprocess,
)


OUT_DIR = "out_2r4c"


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

    print("=" * 60)
    print(f"  2x4 dowel configuration  —  full nonlinear solve")
    print(f"  Output directory: {OUT_DIR}/")
    print(f"  L={L}  H={H}  B={B}  t_plate={t_plate}")
    print(f"  d_dowel={d_dowel}  mesh_size={mesh_size}")
    print(f"  imposed_disp={imposed_disp} mm")
    print(f"  EC5 block shear Rd = {F_ec5_kN} kN")
    print("=" * 60)

    # ── Build geometry + mesh ─────────────────────────────────────────────────
    mapdl, vid_beam, vid_plate, vid_dowels, positions, sz1, sz2 = build_model(
        L=L, H=H, B=B, t_plate=t_plate,
        n_rows=n_rows, n_cols=n_cols,
        d_dowel=d_dowel, mesh_size=mesh_size,
        block_shear=True, clearance=0.5,
        run_location=OUT_DIR,
    )

    n_dowels = len(vid_dowels)
    n_pairs  = n_dowels * 2   # timber + plate pair per dowel

    try:
        # ── Contacts ─────────────────────────────────────────────────────────
        add_contacts(
            mapdl, positions, vid_beam, vid_plate, vid_dowels,
            sz1=sz1, sz2=sz2,
            mu_timber=0.3, mu_plate=0.15, pinb=10,
        )

        mapdl.save("pymapdl_2r4c_presolve", "db")

        # ── Quick verification (2 mm) ─────────────────────────────────────────
        vr = verify_force_transfer(
            mapdl, L=L, H=H, B=B, t_plate=t_plate,
            positions=positions,
            ux_verify=2.0, nsubst=(20, 100, 5),
        )

        if abs(vr["fx_reaction"]) < 10.0:
            # Force balance is the reliable check: beam UX≈0 is expected for
            # stiff timber in compression; SMISC,1 projection underestimates.
            print("\nVerification FAILED — no reaction force at x=0 (contact inactive).")
            sys.exit(1)

        # ── Restore clean presolve state before full solve ────────────────────
        # verify_force_transfer leaves the database in a deformed state.
        # Resume the saved DB so the full solve starts from zero displacement.
        print("\nResuming presolve DB to restore undeformed mesh...")
        mapdl.finish()
        mapdl.resume("pymapdl_2r4c_presolve", "db")
        print("Resume complete — starting full nonlinear solve.")

        # ── Full nonlinear solve ──────────────────────────────────────────────
        add_bcs_and_solve(
            mapdl, L=L, H=H, B=B, t_plate=t_plate,
            imposed_disp=imposed_disp,
            nsubst=(20, 200, 5),
        )

        mapdl.save("pymapdl_2r4c_solved", "db")

        # ── Post-processing + plot ────────────────────────────────────────────
        _postprocess_2r4c(
            mapdl,
            imposed_disp=imposed_disp,
            F_ec5_kN=F_ec5_kN,
            n_pairs=n_pairs,
            positions=positions,
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
    """Return (sy_max, sxy_max) in MPa for timber (mat=1) elements at current result set."""
    def _get(name):
        try:
            return float(mapdl.parameters[name])
        except (KeyError, TypeError, ValueError):
            return 0.0

    mapdl.allsel()
    mapdl.esel("s", "mat", "", 1)   # timber only (avoid underscore-reserved APDL names)
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


def _postprocess_2r4c(mapdl, imposed_disp, F_ec5_kN, n_pairs, positions):
    """Post-process and save force-displacement curve for 2r4c config."""
    import csv
    import matplotlib.pyplot as plt

    mapdl.run("/POST1")
    mapdl.run("INRES,ALL")
    times = mapdl.post_processing.time_values
    print(f"Result sets: {len(times)}")

    if len(times) >= 2 and times[-1] >= 0.999 and times[-2] < 0.99:
        times = times[:-1]
        print(f"  (dropped spurious end-time entry; using {len(times)} result sets)")

    forces_kN = []
    disps_mm  = []

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
        mapdl.allsel()
        mapdl.run("SET,NEXT")
    mapdl.ignore_errors = _prev

    # ── Peak-load global Sy and Sxy in timber ─────────────────────────────────
    peak_idx = forces_kN.index(max(forces_kN)) if forces_kN else 0
    mapdl.run("SET,FIRST")
    for _ in range(peak_idx):
        mapdl.run("SET,NEXT")
    sy_max, sxy_max = _global_timber_stress_max(mapdl)
    print(f"\nPeak-load global timber stresses:")
    print(f"  Sy  max : {sy_max:.3f} MPa   (ft,90,k = 0.50 MPa → ratio {sy_max/0.50:.2f})")
    print(f"  Sxy max : {sxy_max:.3f} MPa  (fv,k    = 3.50 MPa → ratio {sxy_max/3.50:.2f})")

    # Save CSV
    csv_path = os.path.join(OUT_DIR, "force_displacement_2r4c.csv")
    try:
        os.remove(csv_path)
    except OSError:
        pass
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["displacement_mm", "force_kN"])
        w.writerows(zip(disps_mm, forces_kN))
    print(f"Saved {csv_path}")

    # Reload last well-converged substep for contact summary
    mapdl.run("INRES,ALL")
    mapdl.run("SET,LAST")
    mapdl.run("SET,PREV")

    from pymapdl_model import _print_contact_pairs, _print_dowel_displacements
    try:
        _print_contact_pairs(mapdl, n_pairs)
    except Exception as e:
        print(f"WARNING: contact pair summary failed: {e}")
    try:
        _print_dowel_displacements(mapdl, positions)
    except Exception as e:
        print(f"WARNING: dowel displacement summary failed: {e}")

    peak_f = max(forces_kN) if forces_kN else 0.0
    peak_d = disps_mm[forces_kN.index(peak_f)] if forces_kN else 0.0

    # Plot
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(disps_mm, forces_kN, "b-o", markersize=4, label="FEM (2×4 dowels)")
    ax.axhline(
        F_ec5_kN, color="r", linestyle="--", linewidth=1.5,
        label=f"EC5 block shear Rd = {F_ec5_kN:.1f} kN",
    )
    if peak_f > 0:
        ax.annotate(
            f"Peak {peak_f:.1f} kN\n@ {peak_d:.1f} mm",
            xy=(peak_d, peak_f),
            xytext=(peak_d + 0.8, peak_f * 0.88),
            arrowprops=dict(arrowstyle="->", color="navy"),
            color="navy", fontsize=9,
        )

    ax.set_xlabel("Displacement [mm]", fontsize=11)
    ax.set_ylabel("Force [kN]", fontsize=11)
    ax.set_title(
        "Block Shear — Force–Displacement  (2 rows × 4 cols, d=12 mm, GL30h)",
        fontsize=12,
    )
    ax.legend(fontsize=10)
    ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    out_png = os.path.join(OUT_DIR, "force_displacement_2r4c.png")
    plt.savefig(out_png, dpi=150)
    print(f"Saved {out_png}")
    plt.show()

    print(f"\nPeak FEM force : {peak_f:.1f} kN  at  {peak_d:.1f} mm displacement")
    print(f"EC5 block shear: {F_ec5_kN:.1f} kN")
    if peak_f > 0:
        ratio = peak_f / F_ec5_kN
        print(f"FEM/EC5 ratio  : {ratio:.3f}  ({'above' if ratio >= 1 else 'below'} EC5)")


if __name__ == "__main__":
    main()
