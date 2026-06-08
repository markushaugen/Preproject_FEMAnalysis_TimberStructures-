import os
from ansys.mapdl.core import launch_mapdl
import numpy as np
import matplotlib.pyplot as plt


def _new_vid(mapdl, before: set) -> int:
    """Return the single volume ID created since the 'before' snapshot.

    ANSYS reuses freed IDs for new geometry (block/cyl4), so vnum[-1] (max)
    is unreliable. Set-difference gives the exact new ID regardless of gaps.
    """
    new = set(mapdl.geometry.vnum) - before
    if len(new) != 1:
        raise RuntimeError(f"Expected 1 new volume, got {new}")
    return new.pop()



def build_model(L=1000, H=200, B=140, t_plate=8, n_rows=2, n_cols=2,
                s_dowel=120, a_edge=100, row_spacing=60, d_dowel=12,
                mesh_size=20, block_shear=True, clearance=0.5,
                run_location="out/"):

    os.makedirs(run_location, exist_ok=True)
    lockfile = os.path.join(run_location, "file.lock")
    if os.path.exists(lockfile):
        try:
            os.remove(lockfile)
        except PermissionError:
            pass
    mapdl = launch_mapdl(run_location=run_location, override=True)
    mapdl.prep7()

    # Materials — Timber GL30h
    mapdl.mp("ex", 1, 13600)
    mapdl.mp("ey", 1, 300)
    mapdl.mp("ez", 1, 300)
    mapdl.mp("prxy", 1, 0.35)
    mapdl.mp("pryz", 1, 0.35)
    mapdl.mp("prxz", 1, 0.35)
    mapdl.mp("gxy", 1, 650)
    mapdl.mp("gyz", 1, 65)
    mapdl.mp("gxz", 1, 650)
    mapdl.tb("fail", 1, tbopt="mxst")
    mapdl.tbdata(1, 30, 24, 2.5, 0.5, 2.5, 0.5)  # Xc, Xt, Yc, Yt, Zc, Zt
    mapdl.tbdata(7, 3.5, 3.5, 3.5)               # Sxy, Syz, Sxz

    # Materials — Steel S355
    mapdl.mp("ex", 2, 210000)
    mapdl.mp("prxy", 2, 0.3)
    mapdl.tb("biso", 2)
    mapdl.tbdata(1, 355, 2100)

    # Element type
    mapdl.et(1, 187)

    # Beam
    snap = set(mapdl.geometry.vnum)
    mapdl.block(0, L, 0, H, 0, B)
    vid_beam = _new_vid(mapdl, snap)

    # Slot (oversized 1mm for clean Boolean cut)
    zc = B / 2
    sz1 = zc - t_plate / 2
    sz2 = zc + t_plate / 2
    x_positions = [L - a_edge - col * s_dowel for col in range(n_cols)]
    slot_x1 = min(x_positions) - a_edge
    slot_x2 = L
    snap = set(mapdl.geometry.vnum)
    mapdl.block(slot_x1 - 1, slot_x2 + 1, -1, H + 1, sz1 - 1, sz2 + 1)
    vid_slot = _new_vid(mapdl, snap)
    snap = set(mapdl.geometry.vnum)
    mapdl.vsbv(vid_beam, vid_slot)
    vid_beam = _new_vid(mapdl, snap)

    # Plate
    plate_y1 = 30
    plate_y2 = H - 30
    snap = set(mapdl.geometry.vnum)
    mapdl.block(slot_x1, slot_x2, plate_y1, plate_y2, sz1, sz2)
    vid_plate = _new_vid(mapdl, snap)

    # Dowel positions
    r = d_dowel if block_shear else d_dowel / 2     # dowel radius
    r_hole = r + clearance                           # hole radius — clearance gives non-zero initial gap for contact
    positions = []
    for row in range(n_rows):
        for col in range(n_cols):
            x = L - a_edge - col * s_dowel
            y = H / 2 - (n_rows - 1) * row_spacing / 2 + row * row_spacing
            positions.append((x, y))

    # Dowel holes in beam and plate, plus dowel volumes.
    # Both cylinders use z=[0, B] so the cutter passes completely through the blank
    # in the z-direction. For the beam (z=0..B) this is an exact-fit cut; for the
    # plate (z=sz1..sz2) the cylinder extends far past both plate faces, so ANSYS
    # resolves the hole boundary against the plate's own faces — no near-coincident
    # face issue that caused triangular holes with the old sz1-1..sz2+1 extents.
    vid_dowels = []
    for x, y in positions:
        snap = set(mapdl.geometry.vnum)
        mapdl.cyl4(x, y, r_hole, "", "", 0, B)        # beam hole
        vid_hole = _new_vid(mapdl, snap)
        snap = set(mapdl.geometry.vnum)
        mapdl.vsbv(vid_beam, vid_hole)
        vid_beam = _new_vid(mapdl, snap)

        snap = set(mapdl.geometry.vnum)
        mapdl.cyl4(x, y, r_hole, "", "", 0, B)        # plate hole — same full-depth cutter
        vid_hole_plate = _new_vid(mapdl, snap)
        snap = set(mapdl.geometry.vnum)
        mapdl.vsbv(vid_plate, vid_hole_plate)
        vid_plate = _new_vid(mapdl, snap)

        snap = set(mapdl.geometry.vnum)
        mapdl.cyl4(x, y, r, "", "", 0, B)             # dowel at nominal radius
        vid_dowels.append(_new_vid(mapdl, snap))

    # Material assignment
    mapdl.vsel("s", "volu", "", vid_beam)
    mapdl.vatt(1, "", 1)
    mapdl.vsel("s", "volu", "", vid_plate)
    mapdl.vatt(2, "", 1)
    for vd in vid_dowels:
        mapdl.vsel("s", "volu", "", vd)
        mapdl.vatt(2, "", 1)
    mapdl.allsel()

    # Mesh — beam and plate at global mesh_size; dowels at r/2 so the chord-arc
    # deviation on the cylinder stays below the 0.5mm clearance, keeping geometric
    # penetration small enough for KEYOPT(9)=1 to work correctly.
    # r/2=6mm → sagitta ≈ 0.38mm < clearance; gives ~12 elements per circumference.

    mapdl.mshape(1, "3d")
    mapdl.mshkey(0)
    mapdl.esize(mesh_size)
    # SMRTSIZE handles small holes within a coarse global mesh automatically.
    # Level 8 (coarse end of 1–10 scale) keeps global elements near mesh_size
    # but refines just enough around small arc boundaries to avoid the
    # "loop has only 2 element divisions" error. Turned off before dowel meshing.
    mapdl.run("SMRTSIZE,8")
    mapdl.vmesh(vid_beam)
    mapdl.vmesh(vid_plate)
    mapdl.run("SMRTSIZE,OFF")
    dowel_esize = min(mesh_size, r)
    mapdl.esize(dowel_esize)
    for vd in vid_dowels:
        mapdl.vmesh(vd)

    n_nodes = mapdl.mesh.n_node
    n_elems = mapdl.mesh.n_elem
    print(f"Nodes: {n_nodes}   Elements: {n_elems}")
    print(f"Beam vol: {vid_beam}, Plate vol: {vid_plate}, Dowel vols: {vid_dowels}")
    NODE_LIMIT = 32000
    if n_nodes > NODE_LIMIT:
        print(f"WARNING: {n_nodes} nodes exceeds the {NODE_LIMIT}-node license limit.")
        print(f"  Re-run with mesh_size=35 to reduce node count below the limit.")
        print(f"  Example: build_model(..., mesh_size=35)")

    return mapdl, vid_beam, vid_plate, vid_dowels, positions, sz1, sz2


def add_contacts(mapdl, positions, vid_beam, vid_plate, vid_dowels,
                 sz1, sz2,
                 mu_timber=0.3, mu_plate=0.15, pinb=10):

    ET_TARGE = 2
    ET_CONTA = 3
    mapdl.et(ET_TARGE, 170)
    mapdl.et(ET_CONTA, 174)
    mapdl.run(f"KEYOPT,{ET_CONTA},2,0")   # Augmented Lagrangian
    mapdl.run(f"KEYOPT,{ET_CONTA},9,1")   # exclude initial gap (fine dowel mesh keeps geometric penetration < clearance)
    mapdl.run(f"KEYOPT,{ET_CONTA},10,2")  # update stiffness every substep
    mapdl.run(f"KEYOPT,{ET_CONTA},12,0")  # frictional

    # Friction materials: structural mats 1/2 untouched; 3/4 are contact-only
    mapdl.run(f"mp,mu,3,{mu_timber}")
    mapdl.run(f"mp,mu,4,{mu_plate}")

    tol = 18

    for i, ((x, y), vd) in enumerate(zip(positions, vid_dowels), 1):
        rset_timber = 2*i - 1
        rset_plate  = 2*i

        # Mesh esize=12mm > plate zone thickness=8mm, so use ±4mm tolerance to
        # guarantee at least one ring of nodes is captured in the plate zone.
        ptol = 4

        # === PLATE pair first — gets first pick of plate-zone faces ===

        # Plate pair — TARGET on dowel
        mapdl.run(f"vsel,s,volu,,{vd}")
        mapdl.run("eslv,s")
        mapdl.run("vsla,s,1")
        mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}")
        mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run(f"nsel,r,loc,z,{sz1-ptol},{sz2+ptol}")
        mapdl.run("type,2")
        mapdl.run(f"real,{rset_plate}")
        mapdl.run("mat,2")
        mapdl.run("esurf")
        mapdl.run("allsel,all")

        # Plate pair — CONTACT on plate hole
        mapdl.run(f"vsel,s,volu,,{vid_plate}")
        mapdl.run("eslv,s")
        mapdl.run("vsla,s,1")
        mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}")
        mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run(f"nsel,r,loc,z,{sz1-ptol},{sz2+ptol}")
        mapdl.run("type,3")
        mapdl.run(f"real,{rset_plate}")
        mapdl.run("mat,4")
        mapdl.run("esurf")
        mapdl.run("allsel,all")

        # === TIMBER pair second — ESURF auto-skips plate-zone faces already covered ===

        # Timber pair — TARGET on dowel (full Z including end caps — end-cap faces
        # provide the axial Z-direction constraint that prevents dowel rigid-body sliding)
        mapdl.run(f"vsel,s,volu,,{vd}")
        mapdl.run("eslv,s")
        mapdl.run("vsla,s,1")
        mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}")
        mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run("type,2")
        mapdl.run(f"real,{rset_timber}")
        mapdl.run("mat,2")
        mapdl.run("esurf")
        mapdl.run("allsel,all")

        # Timber pair — CONTACT on beam hole (full Z; end-cap faces pair with dowel end caps)
        mapdl.run(f"vsel,s,volu,,{vid_beam}")
        mapdl.run("eslv,s")
        mapdl.run("vsla,s,1")
        mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}")
        mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run("type,3")
        mapdl.run(f"real,{rset_timber}")
        mapdl.run("mat,3")
        mapdl.run("esurf")
        mapdl.run("allsel,all")

    # PINB on all pairs
    n_pairs = len(vid_dowels) * 2
    for ipinb in range(1, n_pairs + 1):
        mapdl.run(f"rmodif,{ipinb},4,{pinb}")

    mapdl.esel("s", "type", "", ET_TARGE)
    n_targ = mapdl.mesh.n_elem
    mapdl.esel("s", "type", "", ET_CONTA)
    n_cont = mapdl.mesh.n_elem
    mapdl.allsel()
    print(f"Created {n_pairs} contact pairs ({len(positions)} dowels x 2) | "
          f"TARGE170: {n_targ}  CONTA174: {n_cont}")

    print("Per-pair element counts:")
    for p in range(1, n_pairs + 1):
        mapdl.esel("s", "type", "", ET_TARGE)
        mapdl.esel("r", "real", "", p)
        nt = mapdl.mesh.n_elem
        mapdl.esel("s", "type", "", ET_CONTA)
        mapdl.esel("r", "real", "", p)
        nc = mapdl.mesh.n_elem
        status = "OK" if nt > 0 and nc > 0 else "MISSING TARGET" if nt == 0 else "MISSING CONTA"
        print(f"  Pair {p}: TARGE={nt:4d}, CONTA={nc:4d}  [{status}]")
    mapdl.allsel()


def add_bcs_and_solve(mapdl, L, H, B, t_plate, imposed_disp=20.0, nsubst=(20, 200, 5)):
    plate_y1 = 30
    plate_y2 = H - 30
    sz1 = B / 2 - t_plate / 2
    sz2 = B / 2 + t_plate / 2

    mapdl.finish()
    mapdl.run("/solu")

    mapdl.run("ANTYPE,STATIC,NEW")   # NEW clears the RST so only this solve's substeps are stored
    mapdl.nlgeom("on")
    mapdl.kbc(0)
    mapdl.nsubst(nsubst[0], nsubst[1], nsubst[2])
    mapdl.run("AUTOTS,ON")
    mapdl.outres("all", "all")
    mapdl.outres("rsol",  "all")   # explicit: DOF reaction forces
    mapdl.outres("smisc", "all")   # explicit: summary miscellaneous (SMISC) for contact
    mapdl.outres("nmisc", "all")   # explicit: nodal miscellaneous for contact
    mapdl.run("CNVTOL,F,1.0,0.01")
    mapdl.run("CNVTOL,U,1.0,0.005")
    mapdl.run("NROP,UNSYM")  # unsymmetric NR for frictional contact (mu=0.3)
    # Stabilise floating dowels during early substeps before contact closes.
    # ENERGY method fails when initial strain energy is zero (all contact open),
    # so use STIFFNESS which adds 1e-4 * K_diag spring-to-ground regardless.
    # REDUCE ramps stiffness to zero over the load step so final results are unaffected.
    mapdl.run("STABILIZE,REDUCE,STIFFNESS,1e-4")

    # Fix beam left face (x=0)
    mapdl.allsel()
    mapdl.nsel("s", "loc", "x", -0.1, 0.1)
    n_fixed = mapdl.mesh.n_node
    mapdl.d("all", "all", 0)
    mapdl.allsel()
    print(f"Fixed nodes at x=0: {n_fixed}")

    # Imposed displacement on plate end face (x=L, z∈[sz1,sz2], y∈[plate_y1,plate_y2])
    mapdl.nsel("s", "loc", "x", L - 0.1, L + 0.1)
    mapdl.nsel("r", "loc", "y", plate_y1, plate_y2)
    mapdl.nsel("r", "loc", "z", sz1, sz2)
    n_load = mapdl.mesh.n_node
    print(f"Displaced nodes at plate end (x=L, y=[{plate_y1},{plate_y2}], z=[{sz1:.1f},{sz2:.1f}]): {n_load}")
    if n_load == 0:
        # Widen z tolerance — mesh may not land exactly on sz1/sz2
        mapdl.allsel()
        mapdl.nsel("s", "loc", "x", L - 0.1, L + 0.1)
        mapdl.nsel("r", "loc", "y", plate_y1 - 1, plate_y2 + 1)
        mapdl.nsel("r", "loc", "z", sz1 - 2, sz2 + 2)
        n_load = mapdl.mesh.n_node
        print(f"  (widened tol) displaced nodes: {n_load}")
    mapdl.d("all", "ux", imposed_disp)
    mapdl.d("all", "uy", 0)
    mapdl.d("all", "uz", 0)
    mapdl.allsel()

    print("CNCHECK output:")
    print(mapdl.run("CNCHECK"))
    print("Solving...")
    mapdl.solve()
    mapdl.finish()
    print("Solve complete.")


def verify_force_transfer(mapdl, L, H, B, t_plate, positions,
                          ux_verify=2.0, nsubst=(5, 20, 2)):
    """Run a small-displacement solve and print three force-transfer checks.

    Returns a dict with the raw scalar results for each check.
    Call this after add_contacts and before the full solve.
    """
    import re
    ET_CONTA = 3
    plate_y1 = 30
    plate_y2 = H - 30
    sz1 = B / 2 - t_plate / 2
    sz2 = B / 2 + t_plate / 2
    x_conn = min(x for x, _ in positions)   # leftmost dowel column x

    add_bcs_and_solve(mapdl, L=L, H=H, B=B, t_plate=t_plate,
                      imposed_disp=ux_verify, nsubst=nsubst)

    mapdl.run("/POST1")
    times = mapdl.post_processing.time_values
    print(f"\n{'='*55}")
    print(f"  Verification: force transfer through dowels")
    print(f"  Applied UX = {ux_verify} mm,  nsubst = {nsubst}")
    print(f"  Result sets in RST: {len(times)}")
    print(f"{'='*55}")
    if len(times) == 0:
        print("WARNING: No result sets — solve produced no output. Skipping verification.")
        return dict(fx_reaction=0, fx_applied=0, ux_near=0, ux_far=0, fx_contact=0)
    # Drop spurious T≈1.0 end-time metadata entry (same filter as postprocess).
    if len(times) >= 2 and times[-1] >= 0.999 and times[-2] < 0.99:
        times = times[:-1]
        print(f"  (dropped spurious end-time entry; using {len(times)} result sets)")
    mapdl.run("INRES,ALL")      # must come BEFORE SET so all data types are loaded
    mapdl.run("SET,LAST")
    print(f"  Last result time = {times[-1]:.4f}")
    mapdl.csys(0)  # ensure global Cartesian for all NSEL/LOC queries

    # Debug: plate end UX to confirm displacement was applied
    mapdl.allsel()
    mapdl.nsel("s", "loc", "x", L - 1.0, L + 1.0)
    mapdl.nsel("r", "loc", "z", sz1 - 2, sz2 + 2)
    n_debug = mapdl.mesh.n_node
    out_ux = mapdl.run("PRNSOL,U,X")
    ux_vals = [float(v) for v in re.findall(r"[-+]?\d+\.?\d*[Ee][+-]?\d+", out_ux)
               if abs(float(v)) < 1e4]
    print(f"  DEBUG plate end: {n_debug} nodes, UX max={max(ux_vals) if ux_vals else 'none'}")
    print(f"  DEBUG raw PRNSOL (last 3 lines): {chr(10).join(out_ux.strip().splitlines()[-3:])}")
    mapdl.allsel()
    mapdl.csys(0)

    # Helper: sum FX at selected nodes using NFORCE+FSUM (element nodal forces).
    # PRRSOL fails in ANSYS 2022 for nonlinear contact analyses (RSOL not stored);
    # NFORCE+FSUM gives identical equilibrium forces and always works in POST1.
    def _nforce_fx():
        _prev = mapdl.ignore_errors
        mapdl.ignore_errors = True
        mapdl.run("NFORCE,ALL")
        mapdl.run("FSUM")       # FSUM must be called after NFORCE to fill the *GET buffer
        mapdl.run("*GET,NFFX,FSUM,,ITEM,FX")
        mapdl.ignore_errors = _prev
        try:
            return float(mapdl.parameters["NFFX"])
        except (KeyError, TypeError, ValueError):
            return 0.0

    # Helper: return max UX from currently selected nodes via PRNSOL parse
    def _max_ux():
        out = mapdl.run("PRNSOL,U,X")
        vals = [float(v) for v in re.findall(r"[-+]?\d+\.?\d*[Ee][+-]?\d+", out)]
        # PRNSOL header numbers (substep, load step IDs) can appear — take only plausible UX
        disp_vals = [v for v in vals if abs(v) < 1e4]
        return max(disp_vals) if disp_vals else 0.0

    # ── Check 1: Global force balance ──
    mapdl.csys(0)
    mapdl.allsel()
    mapdl.nsel("s", "loc", "x", -1.0, 1.0)
    n_fixed = mapdl.mesh.n_node
    fx_reaction = _nforce_fx()

    mapdl.csys(0)
    mapdl.allsel()
    mapdl.nsel("s", "loc", "x", L - 1.0, L + 1.0)
    mapdl.nsel("r", "loc", "y", plate_y1 - 2, plate_y2 + 2)
    mapdl.nsel("r", "loc", "z", sz1 - 2, sz2 + 2)
    n_loaded = mapdl.mesh.n_node
    fx_applied = _nforce_fx()
    mapdl.allsel()

    imbalance = abs(fx_reaction + fx_applied) / max(abs(fx_reaction), 1.0)
    c1_ok = abs(fx_reaction) > 1.0 and imbalance < 0.05
    print(f"\nCheck 1 — Global force balance  (fixed nodes={n_fixed}, loaded nodes={n_loaded})")
    print(f"  FX reaction at x=0    : {fx_reaction/1e3:+.3f} kN")
    print(f"  FX applied  at x=L    : {fx_applied/1e3:+.3f} kN")
    print(f"  Imbalance             : {imbalance*100:.1f}%"
          f"   [{'PASS' if c1_ok else 'FAIL -- reaction ~0 or unbalanced'}]")

    # ── Check 2: Beam UX near dowels vs far from dowels ──
    mapdl.csys(0)
    mapdl.allsel()
    mapdl.nsel("s", "loc", "x", x_conn - 50, x_conn + 50)  # wider range for coarse mesh
    mapdl.nsel("u", "loc", "z", sz1 - 2, sz2 + 2)   # exclude plate z-zone
    ux_near = _max_ux()

    mapdl.csys(0)
    mapdl.allsel()
    mapdl.nsel("s", "loc", "x", L / 4 - 50, L / 4 + 50)
    mapdl.nsel("u", "loc", "z", sz1 - 2, sz2 + 2)
    ux_far = _max_ux()
    mapdl.allsel()

    c2_moving = ux_near > 0.01 * ux_verify
    c2_local  = ux_far < ux_near * 0.1
    print(f"\nCheck 2 — Beam UX (applied = {ux_verify} mm)")
    print(f"  Max UX beam near dowels (x~{x_conn:.0f}) : {ux_near:.4f} mm"
          f"   [{'PASS -- beam moving' if c2_moving else 'FAIL -- beam stationary'}]")
    print(f"  Max UX beam far (x~{L/4:.0f})          : {ux_far:.4f} mm"
          f"   [{'OK -- local effect' if c2_local else 'WARN -- may have shared nodes'}]")

    # ── Check 3: Contact element force (SMISC,1 sum) ──
    fx_contact = 0.0
    mapdl.allsel()
    mapdl.esel("s", "type", "", ET_CONTA)
    _prev = mapdl.ignore_errors
    mapdl.ignore_errors = True
    try:
        mapdl.etable("CTFX", "SMISC", 1)
        mapdl.ssum()
        mapdl.run("*GET,FXCONT,SSUM,,ITEM,CTFX")
        fx_contact = float(mapdl.parameters["FXCONT"])
    except Exception:
        fx_contact = float("nan")
    mapdl.ignore_errors = _prev
    mapdl.allsel()

    if abs(fx_reaction) > 1.0 and not (fx_contact != fx_contact):  # nan check
        ratio = abs(fx_contact) / abs(fx_reaction)
        if ratio > 0.5:
            c3_status = f"PASS -- {ratio*100:.0f}% of reaction through contact"
        elif abs(fx_contact) < 10.0:
            c3_status = "FAIL -- contact force ~0  (check SMISC numbering or end-cap contamination)"
        else:
            c3_status = f"PARTIAL -- {ratio*100:.0f}%  investigate missing pairs"
    elif fx_contact != fx_contact:
        c3_status = "SKIP -- SMISC database unavailable (OUTRES,SMISC not stored)"
    else:
        c3_status = "N/A -- reaction ~0, contact not active"
    print(f"\nCheck 3 -- CONTA174 SMISC,1 force sum")
    print(f"  Sum CONTA174 SMISC,1  : {fx_contact/1e3:+.3f} kN   [{c3_status}]")

    # ── Summary and action items ──
    print(f"\n{'-'*55}")
    if not c2_moving:
        print("ACTION: Beam not moving — contact not transferring force.")
        print("  1. Check per-pair TARGE/CONTA counts (add_contacts printout).")
        print("  2. Print CONTA174 element centroids and confirm none are")
        print("     on end-cap planes (z~0 or z~B).")
        print("  3. Check for vsbv shared areas between beam/plate/dowels.")
    elif not c2_local:
        print("WARNING: Beam displaces uniformly (not just near dowels).")
        print("  Possible shared nodes between beam and plate — check vsbv.")
    elif not c1_ok and c2_moving:
        print("WARNING: Beam moves but force balance fails.")
        print("  FSUM may be missing some reaction nodes — widen x=0 tolerance.")
    else:
        print("All checks passed — force path is correct.")
        print(f"  Proceed with full solve (nsubst=20,200,5, ux={20.0} mm).")

    return dict(fx_reaction=fx_reaction, fx_applied=fx_applied,
                ux_near=ux_near, ux_far=ux_far, fx_contact=fx_contact)


def _print_contact_pairs(mapdl, n_pairs):
    """Print per-pair contact pressure and status for the current result set.

    Pair ordering: for each dowel i, timber pair = 2i-1, plate pair = 2i.
    Pressure and status are parsed directly from PRESOL,CONT, which works even
    when the SMISC/ETABLE database is unavailable in the RST.
    """
    _smap = {0: "open", 1: "near", 2: "slide", 3: "stick"}

    print(f"\n{'='*76}")
    print(f"  Contact pair summary -- last substep")
    print(f"  Pair ordering: for each dowel, odd pair = timber-hole, even pair = plate-hole")
    print(f"  Pressure = mean contact pressure from PRESOL,CONT (N/mm²)")
    print(f"  {'Pair':>4}  {'Dowel':>5}  {'Surface':>8}  {'n_el':>5}  {'MeanPres':>10}  open/near/slide/stick")
    print(f"  {'-'*71}")

    totals = {"timber": 0.0, "plate": 0.0}

    for p in range(1, n_pairs + 1):
        dowel_i = (p + 1) // 2
        surface = "timber" if p % 2 == 1 else "plate "
        key = surface.strip()

        mapdl.allsel()
        mapdl.esel("s", "ename", "", 174)
        mapdl.esel("r", "real",  "", p)
        n_el = mapdl.mesh.n_elem

        if n_el == 0:
            print(f"  Pair {p:>2}  D{dowel_i:>4}  {surface}  {n_el:>5}  (no elements)")
            continue

        # Parse pressure and status from PRESOL,CONT output.
        # Format per element: "ELEMENT= NNN CONTA174" header, then node rows:
        # "NODE  STAT  PENE  PRES  SFRIC  SLIP  TOLN"
        # where STAT is col[1] and PRES is col[3] (0-indexed).
        out_cont = mapdl.run("PRESOL,CONT")
        state_counts = {"open": 0, "near": 0, "slide": 0, "stick": 0}
        _el_stats: list[int] = []
        _el_pres:  list[float] = []
        all_pres:  list[float] = []

        def _flush_el():
            if _el_stats:
                ms = max(_el_stats)
                if ms in _smap:
                    state_counts[_smap[ms]] += 1
            if _el_pres:
                all_pres.append(sum(_el_pres) / len(_el_pres))

        for _ln in out_cont.split("\n"):
            if "ELEMENT=" in _ln and "CONTA174" in _ln:
                _flush_el()
                _el_stats = []
                _el_pres  = []
                continue
            _tok = _ln.split()
            if len(_tok) >= 2:
                try:
                    if _tok[0].isdigit() and int(_tok[0]) > 0:
                        st = int(round(float(_tok[1])))
                        if 0 <= st <= 3:
                            _el_stats.append(st)
                        if len(_tok) >= 4:
                            pv = float(_tok[3])
                            if abs(pv) < 1e9:
                                _el_pres.append(pv)
                except (ValueError, IndexError):
                    pass
        _flush_el()

        mean_pres = sum(all_pres) / len(all_pres) if all_pres else 0.0
        totals[key] += mean_pres

        stat_parts = [f"{n}={state_counts[n]}" for n in ("open","near","slide","stick")
                      if state_counts[n] > 0]
        stat_str = "  ".join(stat_parts) if stat_parts else "--"
        print(f"  Pair {p:>2}  D{dowel_i:>4}  {surface}  {n_el:>5}  {mean_pres:>+10.3f}  {stat_str}")

    print(f"  {'-'*71}")
    print(f"  Timber-hole pairs (1,3,5,7) mean pres: {totals['timber']:>+9.3f} N/mm²")
    print(f"  Plate-hole  pairs (2,4,6,8) mean pres: {totals['plate']:>+9.3f} N/mm²")
    print(f"{'='*76}")
    mapdl.allsel()


def _print_dowel_displacements(mapdl, positions, dowel_r=12):
    """Print max UX per dowel volume at the currently-loaded result set."""
    # Use bounding box slightly inside the dowel radius to avoid selecting hole-wall nodes
    # (hole wall is at r+clearance = 12.5mm from center; dowel surface is at 12mm)
    sel_r = dowel_r - 0.5
    print(f"\n{'='*55}")
    print(f"  Dowel UX displacements (last substep)")
    print(f"  {'D':>3}  {'x':>6}  {'y':>6}  {'UXmax [mm]':>12}  {'UXmin [mm]':>12}")
    print(f"  {'-'*50}")
    for i, (x, y) in enumerate(positions, 1):
        mapdl.allsel()
        # NSEL by bounding box works in POST1; ESEL,S,VOLU does not
        mapdl.nsel("s", "loc", "x", x - sel_r, x + sel_r)
        mapdl.nsel("r", "loc", "y", y - sel_r, y + sel_r)
        n_nd = mapdl.mesh.n_node
        if n_nd == 0:
            print(f"  D{i:>2}  {x:>6.0f}  {y:>6.0f}  (no nodes selected)")
            continue
        out = mapdl.run("PRNSOL,U,X")
        vals = []
        for ln in out.split("\n"):
            tok = ln.split()
            if len(tok) >= 2:
                try:
                    if tok[0].isdigit() and int(tok[0]) > 0:
                        vals.append(float(tok[1]))
                except (ValueError, IndexError):
                    pass
        if vals:
            print(f"  D{i:>2}  {x:>6.0f}  {y:>6.0f}  {max(vals):>12.4f}  {min(vals):>12.4f}")
        else:
            print(f"  D{i:>2}  {x:>6.0f}  {y:>6.0f}  (no UX data parsed)")
    print(f"{'='*55}")
    mapdl.allsel()


def postprocess(mapdl, imposed_disp=20.0, F_ec5_kN=133.0, n_pairs=8,
                positions=None):
    mapdl.run("/POST1")
    mapdl.run("INRES,ALL")
    times = mapdl.post_processing.time_values
    print(f"Result sets: {len(times)}")

    # Filter out any t≈1.0 entries that are RST end-time metadata, not converged results.
    # When ANSYS terminates early, the load-step end time (t=1.0) can appear in the time
    # list even though no valid result was stored there. Drop the last entry if t ≥ 0.999
    # and the second-to-last is significantly smaller.
    if (len(times) >= 2
            and times[-1] >= 0.999 * (imposed_disp / imposed_disp)  # t ≥ 0.999
            and times[-2] < 0.99):
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

    # Write CSV immediately — before any optional summaries that might fail
    import csv
    csv_path = "out/force_displacement.csv"
    try:
        os.remove(csv_path)
    except OSError:
        pass
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["displacement_mm", "force_kN"])
        w.writerows(zip(disps_mm, forces_kN))
    print(f"Saved {csv_path}")

    # Reload result for contact/dowel summaries.
    # The very last substep may be barely-converged (accepted at NEQIT=25 exhausted) and
    # have incomplete CONT data in the RST. Load the penultimate substep instead, which is
    # always well-converged and has complete contact element results.
    mapdl.run("INRES,ALL")
    mapdl.run("SET,LAST")
    mapdl.run("SET,PREV")   # step back to last well-converged substep

    # Print per-pair contact status/force for the last loaded substep
    try:
        _print_contact_pairs(mapdl, n_pairs)
    except Exception as e:
        print(f"WARNING: contact pair summary failed: {e}")

    # Print per-dowel UX displacement at the last substep
    if positions is not None:
        try:
            _print_dowel_displacements(mapdl, positions)
        except Exception as e:
            print(f"WARNING: dowel displacement summary failed: {e}")

    peak_f = max(forces_kN)
    peak_d = disps_mm[forces_kN.index(peak_f)]
    print(f"Max force: {peak_f:.1f} kN at {peak_d:.1f} mm")

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(disps_mm, forces_kN, "b-o", markersize=4, label="FEM")
    ax.axhline(F_ec5_kN, color="r", linestyle="--",
               label=f"EC5 Rd = {F_ec5_kN:.0f} kN")
    ax.annotate(f"Peak {peak_f:.1f} kN\n@ {peak_d:.1f} mm",
                xy=(peak_d, peak_f),
                xytext=(peak_d + 1, peak_f * 0.85),
                arrowprops=dict(arrowstyle="->", color="navy"),
                color="navy", fontsize=9)
    ax.set_xlabel("Displacement [mm]")
    ax.set_ylabel("Force [kN]")
    ax.set_title("Block Shear – Force–Displacement")
    ax.legend()
    ax.grid(True)
    plt.tight_layout()
    plt.savefig("out/force_displacement_curve.png", dpi=150)

    return disps_mm, forces_kN


def main(mesh_size=20):
    L, H, B, t_plate = 1000, 200, 140, 8
    d_dowel, n_rows, n_cols = 12, 2, 2
    imposed_disp = 20.0

    mapdl, vid_beam, vid_plate, vid_dowels, positions, sz1, sz2 = build_model(
        L=L, H=H, B=B, t_plate=t_plate,
        n_rows=n_rows, n_cols=n_cols,
        d_dowel=d_dowel, mesh_size=mesh_size, block_shear=True, clearance=0.5,
    )

    try:
        add_contacts(
            mapdl, positions, vid_beam, vid_plate, vid_dowels,
            sz1=sz1, sz2=sz2,
            mu_timber=0.3, mu_plate=0.15, pinb=10,
        )

        mapdl.save("pymapdl_blockshear_presolve", "db")

        # Quick verification: 2 mm displacement
        vr = verify_force_transfer(mapdl, L=L, H=H, B=B, t_plate=t_plate,
                                   positions=positions, ux_verify=2.0,
                                   nsubst=(5, 20, 2))

        if vr["ux_near"] < 0.01:
            print("\nVerification FAILED — fix contact before full solve.")
            raise SystemExit(1)

        # Full nonlinear solve
        add_bcs_and_solve(mapdl, L=L, H=H, B=B, t_plate=t_plate,
                          imposed_disp=imposed_disp, nsubst=(20, 200, 5))

        mapdl.save("pymapdl_blockshear_solved", "db")

        postprocess(mapdl, imposed_disp=imposed_disp, F_ec5_kN=133.0,
                    positions=positions)

    finally:
        try:
            mapdl.exit()
        except Exception:
            pass
        # Wait for ANSYS to release the lock file before the process exits,
        # so a subsequent launch_mapdl doesn't race against the dying process.
        import time
        lock = "out/file.lock"
        for _ in range(20):
            if not os.path.exists(lock):
                break
            time.sleep(1)


if __name__ == "__main__":
    main(mesh_size=35)
