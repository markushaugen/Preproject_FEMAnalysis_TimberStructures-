"""
Geometry-only (pre-solved) model: 3 rows x 3 columns of dowels.
L=1000, H=240, B=140 mm — dowels at x=[660,780,900], y=[60,120,180].
Builds geometry and mesh, saves DB, then exits — no contacts, no solve.
Run this to check geometry and node count before committing to solve_3x3.py.
"""

import os
import time
from ansys.mapdl.core import launch_mapdl

OUT_DIR = "out_3x3"


def _new_vid(mapdl, before: set) -> int:
    new = set(mapdl.geometry.vnum) - before
    if len(new) != 1:
        raise RuntimeError(f"Expected 1 new volume, got {new}")
    return new.pop()


def build_geometry_only(
    L=1000, H=240, B=140, t_plate=8,
    n_rows=3, n_cols=3,
    s_dowel=120, a_edge=100, row_spacing=60,
    d_dowel=12,
    beam_esize=80,
    plate_esize=25,
    dowel_esize=10,
    clearance=0.5,
):
    zc    = B / 2
    sz1   = zc - t_plate / 2
    sz2   = zc + t_plate / 2
    r_hole = d_dowel / 2 + clearance
    r_dow  = d_dowel / 2

    x_positions = [L - a_edge - col * s_dowel for col in range(n_cols)]
    y_positions = [
        H / 2 - (n_rows - 1) * row_spacing / 2 + row * row_spacing
        for row in range(n_rows)
    ]
    positions = [(x, y) for y in y_positions for x in x_positions]

    slot_x1  = min(x_positions) - a_edge
    slot_x2  = L
    plate_y1 = 30
    plate_y2 = H - 30

    print("=" * 65)
    print("  GEOMETRY PARAMETERS  (n_rows=3, n_cols=3)")
    print("=" * 65)
    print(f"  Beam          : L={L}  H={H}  B={B}  [mm]")
    print(f"  Plate         : t={t_plate} mm  z=[{sz1:.1f}, {sz2:.1f}]  "
          f"y=[{plate_y1}, {plate_y2}]")
    print(f"  Slot (beam)   : x=[{slot_x1}, {slot_x2}]  z=[{sz1:.1f}, {sz2:.1f}]")
    print(f"  Dowel         : d={d_dowel} mm  (r={r_dow})  hole r={r_hole:.1f} mm")
    print(f"  Layout        : {n_rows} rows x {n_cols} cols  ({n_rows*n_cols} dowels)")
    print(f"  a_edge (end)  : {a_edge} mm  = {a_edge/d_dowel:.0f}d")
    print(f"  s_dowel (dx)  : {s_dowel} mm  = {s_dowel/d_dowel:.0f}d")
    print(f"  row_spacing   : {row_spacing} mm  = {row_spacing/d_dowel:.0f}d")
    print(f"  x-positions   : {x_positions}")
    print(f"  y-positions   : {[round(y, 1) for y in y_positions]}")
    print()
    print(f"  {'D':>3}  {'x [mm]':>8}  {'y [mm]':>8}  {'edge_bot':>10}  {'edge_top':>10}")
    print(f"  {'-'*55}")
    for i, (x, y) in enumerate(positions, 1):
        edge_bot = y - r_hole
        edge_top = H - y - r_hole
        flag = "  <-- tight" if min(edge_bot, edge_top) < 3 * d_dowel else ""
        print(f"  D{i:>2}  {x:>8.0f}  {y:>8.1f}  {edge_bot:>10.1f}  {edge_top:>10.1f}{flag}")
    print(f"  {'-'*55}")
    print(f"  EC5 a_4,t min = max(3d={3*d_dowel}, 40) = 40 mm  "
          f"[outer edge = {min(y_positions)-r_hole:.1f} mm]")
    print(f"  beam_esize    : {beam_esize} mm")
    print(f"  plate_esize   : {plate_esize} mm")
    print(f"  dowel_esize   : {dowel_esize} mm")
    print("=" * 65)

    os.makedirs(OUT_DIR, exist_ok=True)
    lockfile = os.path.join(OUT_DIR, "file.lock")
    if os.path.exists(lockfile):
        try:
            os.remove(lockfile)
        except PermissionError:
            import subprocess
            subprocess.call(
                ["taskkill", "/F", "/IM", "ANSYS.exe", "/T"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(3)
            try:
                os.remove(lockfile)
            except OSError:
                pass

    mapdl = launch_mapdl(run_location=OUT_DIR + "/", override=True)
    mapdl.prep7()

    mapdl.mp("ex",   1, 13600);  mapdl.mp("ey",  1, 300);   mapdl.mp("ez",   1, 300)
    mapdl.mp("prxy", 1, 0.35);   mapdl.mp("pryz",1, 0.35);  mapdl.mp("prxz", 1, 0.35)
    mapdl.mp("gxy",  1, 650);    mapdl.mp("gyz", 1, 65);    mapdl.mp("gxz",  1, 650)
    mapdl.mp("ex",   2, 210000); mapdl.mp("prxy",2, 0.3)
    mapdl.et(1, 187)

    snap = set(mapdl.geometry.vnum)
    mapdl.block(0, L, 0, H, 0, B)
    vid_beam = _new_vid(mapdl, snap)

    # No z-oversize on slot: sz1/sz2 match plate faces exactly
    snap = set(mapdl.geometry.vnum)
    mapdl.block(slot_x1 - 1, slot_x2 + 1, -1, H + 1, sz1, sz2)
    vid_slot = _new_vid(mapdl, snap)
    snap = set(mapdl.geometry.vnum)
    mapdl.vsbv(vid_beam, vid_slot)
    vid_beam = _new_vid(mapdl, snap)

    snap = set(mapdl.geometry.vnum)
    mapdl.block(slot_x1, slot_x2, plate_y1, plate_y2, sz1, sz2)
    vid_plate = _new_vid(mapdl, snap)

    vid_dowels = []
    for x, y in positions:
        snap = set(mapdl.geometry.vnum)
        mapdl.cyl4(x, y, r_hole, "", "", 0, B)
        vid_hole = _new_vid(mapdl, snap)
        snap = set(mapdl.geometry.vnum)
        mapdl.vsbv(vid_beam, vid_hole)
        vid_beam = _new_vid(mapdl, snap)

        snap = set(mapdl.geometry.vnum)
        mapdl.cyl4(x, y, r_hole, "", "", 0, B)
        vid_hole_plate = _new_vid(mapdl, snap)
        snap = set(mapdl.geometry.vnum)
        mapdl.vsbv(vid_plate, vid_hole_plate)
        vid_plate = _new_vid(mapdl, snap)

        snap = set(mapdl.geometry.vnum)
        mapdl.cyl4(x, y, r_dow, "", "", 0, B)
        vid_dowels.append(_new_vid(mapdl, snap))

    mapdl.vsel("s", "volu", "", vid_beam);  mapdl.vatt(1, "", 1)
    mapdl.vsel("s", "volu", "", vid_plate); mapdl.vatt(2, "", 1)
    for vd in vid_dowels:
        mapdl.vsel("s", "volu", "", vd);    mapdl.vatt(2, "", 1)
    mapdl.allsel()

    mapdl.mshape(1, "3d")
    mapdl.mshkey(0)

    mapdl.esize(beam_esize)
    mapdl.run("SMRTSIZE,10")
    mapdl.vmesh(vid_beam)
    mapdl.run("SMRTSIZE,OFF")

    mapdl.esize(plate_esize)
    mapdl.run("SMRTSIZE,10")
    mapdl.vmesh(vid_plate)
    mapdl.run("SMRTSIZE,OFF")

    mapdl.esize(dowel_esize)
    for vd in vid_dowels:
        mapdl.vmesh(vd)

    n_nodes = mapdl.mesh.n_node
    n_elems = mapdl.mesh.n_elem
    print(f"\nMesh: {n_nodes} nodes,  {n_elems} elements")
    print(f"Beam vol: {vid_beam},  Plate vol: {vid_plate},  Dowel vols: {vid_dowels}")

    NODE_LIMIT = 32000
    if n_nodes > NODE_LIMIT:
        print(f"WARNING: {n_nodes} nodes exceeds {NODE_LIMIT}-node license limit.")
        print(f"  In solve_3x3.py use mesh_size=40 or larger to reduce count.")

    mapdl.save("pymapdl_presolved_3x3", "db")
    print(f"Saved: {OUT_DIR}/pymapdl_presolved_3x3.db")

    try:
        mapdl.exit()
    except Exception:
        pass

    lock = os.path.join(OUT_DIR, "file.lock")
    for _ in range(20):
        if not os.path.exists(lock):
            break
        time.sleep(1)

    return positions, sz1, sz2


if __name__ == "__main__":
    build_geometry_only()
