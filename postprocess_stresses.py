"""
Standalone post-processor: extract peak Sy and Sxy from existing ANSYS result files.

Reads the RST in the specified run_location (default "out/") and prints
the global max Sy and Sxy in timber (type=1) elements at the peak-force substep.

Usage:
    # 4x2 configuration (4 rows x 2 cols):
    python postprocess_stresses.py --rst-name pymapdl_presolved_4r2c

    # 2x4 configuration (2 rows x 4 cols):
    python postprocess_stresses.py --rst-name pymapdl_presolved_2r4c

    # custom:
    python postprocess_stresses.py --rst-name <jobname> --run-loc out
"""

import argparse
import os
import time
import subprocess


# GL30h characteristic strengths [MPa]
FT90K = 0.50
FVK   = 3.50


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--run-loc",  default="out",
                   help="MAPDL run_location directory (default: out)")
    p.add_argument("--rst-name", default="pymapdl_presolved_4r2c",
                   help="RST jobname without extension "
                        "(default: pymapdl_presolved_4r2c for 4x2; "
                        "use pymapdl_presolved_2r4c for 2x4)")
    p.add_argument("--imposed-disp", type=float, default=20.0,
                   help="Imposed displacement used in the solve [mm] (default: 20)")
    return p.parse_args()


def _clear_lock(run_loc):
    lockfile = os.path.join(run_loc, "file.lock")
    if os.path.exists(lockfile):
        try:
            os.remove(lockfile)
        except PermissionError:
            subprocess.call(["taskkill", "/F", "/IM", "ANSYS.exe", "/T"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            try:
                os.remove(lockfile)
            except OSError:
                pass


def _global_timber_stress_max(mapdl, verbose=True):
    """Return (sy_max, sxy_max) in MPa for timber (mat=1) elements at current set.

    Uses material-1 selection (not type-based) so it works regardless of whether
    contact element types are present in the model. Avoids underscore-prefixed
    APDL names which ANSYS reserves for internal use.
    """
    def _get(name):
        try:
            return float(mapdl.parameters[name])
        except (KeyError, TypeError, ValueError):
            return 0.0

    mapdl.allsel()
    # Select timber (mat=1) SOLID elements only — exclude contact types
    mapdl.esel("s", "mat", "", 1)
    n_el = mapdl.mesh.n_elem
    if verbose:
        print(f"  Timber elements selected (mat=1): {n_el}")
    if n_el == 0:
        # Fallback: try type=1 (geometry-only models have only one element type)
        mapdl.allsel()
        mapdl.esel("s", "type", "", 1)
        n_el = mapdl.mesh.n_elem
        if verbose:
            print(f"  Fallback type=1 selection: {n_el} elements")
    if n_el == 0:
        if verbose:
            print("  WARNING: no timber elements found — stress will be 0")
        mapdl.allsel()
        return 0.0, 0.0

    # Avoid underscore-prefixed names (reserved by ANSYS)
    mapdl.run("ETABLE,PCSY, S,Y")
    mapdl.run("ETABLE,PCSXY,S,XY")
    mapdl.run("*GET,PCSMX1,ETAB,EXTR,PCSY, MAX")
    mapdl.run("*GET,PCSMN1,ETAB,EXTR,PCSY, MIN")
    mapdl.run("*GET,PCSMX2,ETAB,EXTR,PCSXY,MAX")
    mapdl.run("*GET,PCSMN2,ETAB,EXTR,PCSXY,MIN")

    sy  = max(abs(_get("PCSMX1")), abs(_get("PCSMN1")))
    sxy = max(abs(_get("PCSMX2")), abs(_get("PCSMN2")))
    if verbose:
        print(f"  Raw ETABLE: SY=[{_get('PCSMX1'):.4f}, {_get('PCSMN1'):.4f}]  "
              f"SXY=[{_get('PCSMX2'):.4f}, {_get('PCSMN2'):.4f}]")
    mapdl.allsel()
    return sy, sxy


def main():
    args = parse_args()
    _clear_lock(args.run_loc)

    rst_path = os.path.join(args.run_loc, f"{args.rst_name}.rst")
    if not os.path.exists(rst_path):
        print(f"ERROR: RST not found: {rst_path}")
        print("Available primary RST files in the run directory (> 10 MB):")
        for f in sorted(os.listdir(args.run_loc)):
            if (f.endswith(".rst")
                    and not any(f.endswith(f"{i}.rst") for i in range(4))
                    and os.path.getsize(os.path.join(args.run_loc, f)) > 10 * 1024 * 1024):
                sz = os.path.getsize(os.path.join(args.run_loc, f)) / 1024 / 1024
                print(f"  {f}  ({sz:.0f} MB)")
        return

    from ansys.mapdl.core import launch_mapdl
    mapdl = launch_mapdl(run_location=args.run_loc, override=True)

    try:
        mapdl.run("/POST1")
        mapdl.run(f"FILE,{args.rst_name}")
        mapdl.run("INRES,ALL")

        times = mapdl.post_processing.time_values
        print(f"Result sets in {rst_path}: {len(times)}")

        if len(times) == 0:
            print("No results found in RST — may be a geometry-only (pre-solve) file.")
            return

        if len(times) >= 2 and times[-1] >= 0.999 and times[-2] < 0.99:
            times = times[:-1]

        # ── Model diagnostics: show what element types/materials exist ─────────
        mapdl.run("SET,FIRST")
        mapdl.allsel()
        print(f"\nModel info:")
        print(f"  Nodes   : {mapdl.mesh.n_node}")
        print(f"  Elements: {mapdl.mesh.n_elem}")
        for mat_id in range(1, 5):
            mapdl.allsel()
            mapdl.esel("s", "mat", "", mat_id)
            n = mapdl.mesh.n_elem
            if n > 0:
                print(f"  mat={mat_id}: {n} elements")
        prev = mapdl.ignore_errors
        mapdl.ignore_errors = True
        for typ_id in range(1, 6):
            mapdl.allsel()
            mapdl.esel("s", "type", "", typ_id)
            n = mapdl.mesh.n_elem
            if n > 0:
                print(f"  type={typ_id}: {n} elements")
        mapdl.ignore_errors = prev
        mapdl.allsel()

        # Probe x=0 nodes for reaction force reference
        mapdl.nsel("s", "loc", "x", -0.1, 0.1)
        n_fixed = mapdl.mesh.n_node
        print(f"  Nodes at x=0 (expected fixed face): {n_fixed}")
        mapdl.allsel()

        # ── Force extraction ──────────────────────────────────────────────────
        forces_kN = []
        disps_mm  = []

        mapdl.run("SET,FIRST")
        prev = mapdl.ignore_errors
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
            disps_mm.append(t * args.imposed_disp)
            mapdl.allsel()
            mapdl.run("SET,NEXT")
        mapdl.ignore_errors = prev

        print(f"\nForce-displacement (N->kN divided by 1000):")
        for d, f in zip(disps_mm, forces_kN):
            print(f"  d={d:.1f} mm  F={f:.1f} kN")

        peak_f   = max(forces_kN)
        peak_idx = forces_kN.index(peak_f)
        peak_d   = disps_mm[peak_idx]

        print(f"\nPeak FEM force: {peak_f:.1f} kN  at  {peak_d:.1f} mm")

        # Load the peak substep by time value (robust — no SET,NEXT counting)
        t_peak = times[peak_idx]
        mapdl.run(f"SET,,,,,,{t_peak:.6f}")

        sy_max, sxy_max = _global_timber_stress_max(mapdl, verbose=True)

        print(f"\n{'='*50}")
        print(f"  Peak-load global timber stresses")
        print(f"  Sy  max : {sy_max:.3f} MPa   (ft,90,k={FT90K} MPa -> {sy_max/FT90K:.2f})")
        print(f"  Sxy max : {sxy_max:.3f} MPa  (fv,k   ={FVK} MPa  -> {sxy_max/FVK:.2f})")
        print(f"{'='*50}")

    finally:
        try:
            mapdl.exit()
        except Exception:
            pass
        lock = os.path.join(args.run_loc, "file.lock")
        for _ in range(20):
            if not os.path.exists(lock):
                break
            time.sleep(1)


if __name__ == "__main__":
    main()
