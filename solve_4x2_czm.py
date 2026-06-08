"""
Block shear CZM model — 4x2 dowel connection.

The beam is pre-split into 4 spatial regions at the 3 block shear failure planes:
  bottom shear: y = 50 mm   (below y=60 - r_hole=53.5)
  top shear:    y = 250 mm  (above y=240 + r_hole=246.5)
  tension:      x = 772 mm  (left of x=780 - r_hole=773.5)

Cohesive zone at the failure planes is implemented with CONTA174/TARGE170 using
KEYOPT(12)=3 (always-bonded with CZM debonding) and TB,CZM,CBDE material.
This does NOT require shared mesh topology — it works across independent meshes.

Standard 12 mm dowels (block_shear=False).
EC5 combined formula: (A_nett*ft0k + A_netv*fvk/sqrt(3)) / gM = 550 kN.
"""

import os, time, subprocess, csv
from ansys.mapdl.core import launch_mapdl
import matplotlib.pyplot as plt

# ── Parameters ────────────────────────────────────────────────────────────────
L, H, B, t_plate    = 1000, 300, 140, 8
n_rows, n_cols      = 4, 2
d_dowel, clearance  = 12, 0.5
s_dowel, a_edge, row_spacing = 120, 100, 60
mesh_size           = 35
imposed_disp        = 20.0
F_ec5_kN            = 550.2

r_dow   = d_dowel / 2
r_hole  = r_dow + clearance      # 6.5 mm
sz1     = B/2 - t_plate/2        # 66.0 mm
sz2     = B/2 + t_plate/2        # 74.0 mm

x_cols    = [L - a_edge - c*s_dowel for c in range(n_cols)]   # [900, 780]
y_rows    = [H/2 - (n_rows-1)*row_spacing/2 + r*row_spacing
             for r in range(n_rows)]                           # [60,120,180,240]
positions = [(x, y) for y in y_rows for x in x_cols]
slot_x1   = min(x_cols) - a_edge                               # 680
plate_y1, plate_y2 = 30, H - 30                                # 30, 270

# CZM failure plane positions (safely outside hole edges)
y_czm_bot = 50.0     # hole bottom = 60 - 6.5 = 53.5 → 50 is safe
y_czm_top = 250.0    # hole top    = 240 + 6.5 = 246.5 → 250 is safe
x_czm     = 772.0    # hole left   = 780 - 6.5 = 773.5 → 772 is safe

# CZM material parameters (TB,CZM,CBDE: sigma_max, tau_max, GIc, GIIc)
# Tension plane (normal=X, tension // grain):
#   sigma_max = ft0k/gM = 24/1.3 = 18.46 MPa
#   tau_max   = fvk/(sqrt(3)*gM) = 3.5/2.252 = 1.554 MPa
#   GIc  = 1.5 N/mm,  GIIc = 1.5 N/mm
CZM_TENSION = (18.46, 1.554, 1.5, 1.5)

# Shear planes (normal=Y, shear // grain):
#   sigma_max = ft90k/gM = 0.5/1.3 = 0.38 MPa (weak opening, prevents flying apart)
#   tau_max   = same 1.554 MPa
#   GIc  = 0.1 N/mm (brittle perp grain),  GIIc = 1.5 N/mm
CZM_SHEAR   = (0.38, 1.554, 0.1, 1.5)

# ── Element type numbers ──────────────────────────────────────────────────────
ET_SOLID  = 1    # SOLID187
ET_TARGE  = 2    # TARGE170  (dowel contact)
ET_CONTA  = 3    # CONTA174  (dowel contact, frictional)
ET_CZM_T  = 5    # TARGE170  (CZM plane target)
ET_CZM_C  = 6    # CONTA174  (CZM plane contact, bonded+debonding)
ET_BOND_T = 7    # TARGE170  (permanent bond — non-failure interfaces)
ET_BOND_C = 8    # CONTA174  (permanent bond — no debonding)

# Real constant sets: dowel pairs use 1–16, CZM pairs use 17–19, bonds use 20–21
RSET_CZM_BOT  = 17
RSET_CZM_TOP  = 18
RSET_CZM_LEFT = 19
RSET_BOND_BOT = 20   # y=50,  x=[0, x_czm]: vlof/vlob ↔ vlef/vleb
RSET_BOND_TOP = 21   # y=250, x=[0, x_czm]: vuuf/vuub ↔ vlef/vleb

# ── Helpers ───────────────────────────────────────────────────────────────────
def _nvid(mapdl, before):
    new = set(mapdl.geometry.vnum) - before
    if len(new) != 1:
        raise RuntimeError(f"Expected 1 new volume, got {new}")
    return new.pop()


def _clear_lock():
    lf = os.path.join("out", "file.lock")
    if os.path.exists(lf):
        try:
            os.remove(lf)
        except PermissionError:
            subprocess.call(["taskkill", "/F", "/IM", "ANSYS.exe", "/T"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            try:
                os.remove(lf)
            except OSError:
                pass


# ── Geometry + mesh ───────────────────────────────────────────────────────────
def build(mapdl):
    mapdl.prep7()

    # --- Materials ---
    # Timber GL30h (mat 1)
    mapdl.mp("ex",  1, 13600); mapdl.mp("ey",  1, 300);   mapdl.mp("ez",  1, 300)
    mapdl.mp("prxy",1, 0.35);  mapdl.mp("pryz",1, 0.35);  mapdl.mp("prxz",1, 0.35)
    mapdl.mp("gxy", 1, 650);   mapdl.mp("gyz", 1, 65);    mapdl.mp("gxz", 1, 650)

    # Steel S355 (mat 2)
    mapdl.mp("ex",  2, 210000); mapdl.mp("prxy",2, 0.3)
    mapdl.tb("biso",2); mapdl.tbdata(1, 355, 2100)

    # Friction (mat 3 = timber mu=0.3, mat 4 = plate mu=0.15)
    mapdl.run("mp,mu,3,0.3"); mapdl.run("mp,mu,4,0.15")

    # CZM mat 5 = tension plane, CZM mat 6 = shear planes
    mapdl.tb("czm", 5, ntemp=1, tbopt="cbde"); mapdl.tbdata(1, *CZM_TENSION)
    mapdl.tb("czm", 6, ntemp=1, tbopt="cbde"); mapdl.tbdata(1, *CZM_SHEAR)

    # --- Element types ---
    mapdl.et(ET_SOLID, 187)
    mapdl.et(ET_TARGE, 170)
    mapdl.et(ET_CONTA, 174)
    mapdl.et(ET_CZM_T, 170)
    mapdl.et(ET_CZM_C, 174)
    mapdl.et(ET_BOND_T, 170)
    mapdl.et(ET_BOND_C, 174)

    # CZM contact settings (bonded with debonding via TB,CZM)
    mapdl.run(f"KEYOPT,{ET_CZM_C},12,3")   # bonded — debonding governed by TB,CZM
    mapdl.run(f"KEYOPT,{ET_CZM_C},9,0")    # include initial gap/penetration
    mapdl.run(f"KEYOPT,{ET_CZM_C},2,0")    # augmented Lagrangian
    mapdl.run(f"KEYOPT,{ET_CZM_C},10,2")   # update contact stiffness each substep

    # Permanent bond settings (no debonding — holds non-failure interfaces together)
    mapdl.run(f"KEYOPT,{ET_BOND_C},12,5")  # bonded always, no separation allowed
    mapdl.run(f"KEYOPT,{ET_BOND_C},9,0")   # include initial gap/penetration
    mapdl.run(f"KEYOPT,{ET_BOND_C},2,2")   # penalty method (more stable for permanent bonds)

    # --- Beam: 4 spatial regions × 2 z-halves = 8 volumes ---
    # z-split at sz1/sz2 creates the slot implicitly.
    # Region   x-range        y-range         Note
    # lower    [0, L]         [0,   50]        stays fixed, bonded via CZM
    # upper    [0, L]         [250, H]         stays fixed, bonded via CZM
    # left     [0,  772]      [50,  250]       stays fixed, bonded via CZM
    # block    [772, L]       [50,  250]  ←    PULL-OUT BLOCK (fails via CZM)

    def bpair(x1, x2, y1, y2):
        s = set(mapdl.geometry.vnum); mapdl.block(x1, x2, y1, y2, 0,   sz1); vf = _nvid(mapdl, s)
        s = set(mapdl.geometry.vnum); mapdl.block(x1, x2, y1, y2, sz2, B);   vb = _nvid(mapdl, s)
        return vf, vb

    vlof, vlob = bpair(0,     L,     0,         y_czm_bot)
    vuuf, vuub = bpair(0,     L,     y_czm_top, H)
    vlef, vleb = bpair(0,     x_czm, y_czm_bot, y_czm_top)
    vblf, vblb = bpair(x_czm, L,     y_czm_bot, y_czm_top)

    # --- Plate ---
    s = set(mapdl.geometry.vnum)
    mapdl.block(slot_x1, L, plate_y1, plate_y2, sz1, sz2)
    vpl = _nvid(mapdl, s)

    # --- Dowel holes (block + plate only) and dowel cylinders ---
    # All dowels are at x=[780,900] which is > x_czm=772 → no holes in left/lower/upper.
    vid_dowels = []
    for x, y in positions:
        s = set(mapdl.geometry.vnum); mapdl.cyl4(x, y, r_hole, "", "", 0,   sz1); vh = _nvid(mapdl, s)
        s = set(mapdl.geometry.vnum); mapdl.vsbv(vblf, vh);                        vblf = _nvid(mapdl, s)

        s = set(mapdl.geometry.vnum); mapdl.cyl4(x, y, r_hole, "", "", sz2, B);   vh = _nvid(mapdl, s)
        s = set(mapdl.geometry.vnum); mapdl.vsbv(vblb, vh);                        vblb = _nvid(mapdl, s)

        s = set(mapdl.geometry.vnum); mapdl.cyl4(x, y, r_hole, "", "", sz1, sz2); vh = _nvid(mapdl, s)
        s = set(mapdl.geometry.vnum); mapdl.vsbv(vpl,  vh);                        vpl  = _nvid(mapdl, s)

        s = set(mapdl.geometry.vnum); mapdl.cyl4(x, y, r_dow, "", "", 0, B)
        vid_dowels.append(_nvid(mapdl, s))

    # --- Material assignment ---
    for vid in [vlof, vlob, vuuf, vuub, vlef, vleb, vblf, vblb]:
        mapdl.vsel("s", "volu", "", vid); mapdl.vatt(1, "", 1)
    mapdl.vsel("s", "volu", "", vpl);   mapdl.vatt(2, "", 1)
    for vd in vid_dowels:
        mapdl.vsel("s", "volu", "", vd); mapdl.vatt(2, "", 1)
    mapdl.allsel()

    # --- Mesh (independent per-volume, no shared topology needed for CZM contact) ---
    mapdl.mshape(1, "3d"); mapdl.mshkey(0); mapdl.esize(mesh_size)
    for vid in [vlof, vlob, vuuf, vuub, vlef, vleb, vblf, vblb, vpl]:
        mapdl.vmesh(vid)
    mapdl.esize(min(mesh_size, r_dow))
    for vd in vid_dowels:
        mapdl.vmesh(vd)

    print(f"Mesh: {mapdl.mesh.n_node} nodes, {mapdl.mesh.n_elem} elements")

    return mapdl, vlof, vlob, vuuf, vuub, vlef, vleb, vblf, vblb, vpl, vid_dowels


# ── Contacts (dowel friction + CZM failure planes) ────────────────────────────
def add_contacts(mapdl, vlof, vlob, vuuf, vuub, vlef, vleb, vblf, vblb, vpl, vid_dowels):

    # --- Dowel frictional contacts (same as pymapdl_model.py) ---
    mapdl.run(f"KEYOPT,{ET_CONTA},2,0")   # augmented Lagrangian
    mapdl.run(f"KEYOPT,{ET_CONTA},9,1")   # exclude initial gap
    mapdl.run(f"KEYOPT,{ET_CONTA},10,2")  # update stiffness
    mapdl.run(f"KEYOPT,{ET_CONTA},12,0")  # frictional

    tol, ptol = 18, 4

    for i, ((x, y), vd) in enumerate(zip(positions, vid_dowels), 1):
        rset_t = 2*i - 1
        rset_p = 2*i

        # Plate pair — TARGET on dowel (plate z-zone)
        mapdl.vsel("s","volu","",vd); mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}"); mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run(f"nsel,r,loc,z,{sz1-ptol},{sz2+ptol}")
        mapdl.type(ET_TARGE); mapdl.run(f"real,{rset_p}"); mapdl.mat(2); mapdl.run("esurf"); mapdl.allsel()

        # Plate pair — CONTACT on plate hole
        mapdl.vsel("s","volu","",vpl); mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}"); mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run(f"nsel,r,loc,z,{sz1-ptol},{sz2+ptol}")
        mapdl.type(ET_CONTA); mapdl.run(f"real,{rset_p}"); mapdl.mat(4); mapdl.run("esurf"); mapdl.allsel()

        # Timber pair — TARGET on dowel (exclude end caps and slot faces)
        mapdl.vsel("s","volu","",vd); mapdl.run("nsla,s,1")
        mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}"); mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
        mapdl.run(f"nsel,u,loc,z,0,1"); mapdl.run(f"nsel,u,loc,z,{B-1},{B}")
        mapdl.run(f"nsel,u,loc,z,{sz1-1},{sz2+1}")   # exclude flat slot faces
        mapdl.type(ET_TARGE); mapdl.run(f"real,{rset_t}"); mapdl.mat(2); mapdl.run("esurf"); mapdl.allsel()

        # Timber pair — CONTACT on block beam hole (exclude end caps and slot faces)
        for vb in (vblf, vblb):
            mapdl.vsel("s","volu","",vb); mapdl.run("nsla,s,1")
            mapdl.run(f"nsel,r,loc,x,{x-tol},{x+tol}"); mapdl.run(f"nsel,r,loc,y,{y-tol},{y+tol}")
            mapdl.run(f"nsel,u,loc,z,0,1"); mapdl.run(f"nsel,u,loc,z,{B-1},{B}")
            mapdl.run(f"nsel,u,loc,z,{sz1-1},{sz2+1}")   # exclude flat slot faces
            mapdl.type(ET_CONTA); mapdl.run(f"real,{rset_t}"); mapdl.mat(3); mapdl.run("esurf"); mapdl.allsel()

    n_dowel_pairs = len(vid_dowels) * 2
    for p in range(1, n_dowel_pairs + 1):
        mapdl.run(f"rmodif,{p},4,10")   # PINB=10

    # --- CZM contact pairs at the 3 block shear failure planes ---
    # KEYOPT(ET_CZM_C, 12) = 3: always bonded, debonds when traction exceeds TB,CZM criterion.

    czm_pinb = 10   # mm — enough to bridge mesh gap at failure planes

    def czm_pair(rset, mat_czm, axis, val, xlo, xhi, ylo, yhi, tgt_vids, cnt_vids):
        """Create one CZM target+contact pair at a plane defined by axis=val."""
        eps = 1.5  # location tolerance [mm]

        # TARGET on the "fixed" side
        for vid in tgt_vids:
            mapdl.vsel("s","volu","",vid); mapdl.run("nsla,s,1")
            mapdl.run(f"nsel,r,loc,x,{xlo},{xhi}")
            mapdl.run(f"nsel,r,loc,y,{ylo},{yhi}")
            if axis == "x":
                mapdl.run(f"nsel,r,loc,x,{val-eps},{val+eps}")
            elif axis == "y":
                mapdl.run(f"nsel,r,loc,y,{val-eps},{val+eps}")
            mapdl.type(ET_CZM_T); mapdl.run(f"real,{rset}"); mapdl.mat(mat_czm)
            mapdl.run("esurf"); mapdl.allsel()

        # CONTACT on the block side
        for vid in cnt_vids:
            mapdl.vsel("s","volu","",vid); mapdl.run("nsla,s,1")
            mapdl.run(f"nsel,r,loc,x,{xlo},{xhi}")
            mapdl.run(f"nsel,r,loc,y,{ylo},{yhi}")
            if axis == "x":
                mapdl.run(f"nsel,r,loc,x,{val-eps},{val+eps}")
            elif axis == "y":
                mapdl.run(f"nsel,r,loc,y,{val-eps},{val+eps}")
            mapdl.type(ET_CZM_C); mapdl.run(f"real,{rset}"); mapdl.mat(mat_czm)
            mapdl.run("esurf"); mapdl.allsel()

        mapdl.run(f"rmodif,{rset},4,{czm_pinb}")

    # Corner trim: exclude 5 mm band at the x=772/y=50 and x=772/y=250 corners
    # to prevent dual-constraint overconstraint where the planes meet.
    corner = 5.0

    # Bottom shear plane y=50 (mat 6): start at x=x_czm+corner to clear tension corner
    czm_pair(RSET_CZM_BOT, 6, "y", y_czm_bot,
             x_czm + corner, L, -1, y_czm_bot + 1,
             [vlof, vlob], [vblf, vblb])

    # Top shear plane y=250 (mat 6): same x offset
    czm_pair(RSET_CZM_TOP, 6, "y", y_czm_top,
             x_czm + corner, L, y_czm_top - 1, H + 1,
             [vuuf, vuub], [vblf, vblb])

    # Tension plane x=772 (mat 5): trim y-range away from both shear corners
    czm_pair(RSET_CZM_LEFT, 5, "x", x_czm,
             -1, x_czm + 1, y_czm_bot + corner, y_czm_top - corner,
             [vlef, vleb], [vblf, vblb])

    # --- Permanent bonds at non-failure shear interfaces ---
    # The shear planes at y=50 and y=250 extend over the full x-range [0,L].
    # Only x>[x_czm] is a failure plane (CZM above). The x<[x_czm] portion must be
    # permanently bonded to hold the lower/upper/left blocks together.
    bond_pinb = 10
    eps = 1.5

    def bond_side(rset, val_y, xhi, tgt_vids, cnt_vids):
        for vid in tgt_vids:
            mapdl.vsel("s","volu","",vid); mapdl.run("nsla,s,1")
            mapdl.run(f"nsel,r,loc,x,0,{xhi}")
            mapdl.run(f"nsel,r,loc,y,{val_y-eps},{val_y+eps}")
            mapdl.type(ET_BOND_T); mapdl.run(f"real,{rset}"); mapdl.mat(1)
            mapdl.run("esurf"); mapdl.allsel()
        for vid in cnt_vids:
            mapdl.vsel("s","volu","",vid); mapdl.run("nsla,s,1")
            mapdl.run(f"nsel,r,loc,x,0,{xhi}")
            mapdl.run(f"nsel,r,loc,y,{val_y-eps},{val_y+eps}")
            mapdl.type(ET_BOND_C); mapdl.run(f"real,{rset}"); mapdl.mat(1)
            mapdl.run("esurf"); mapdl.allsel()
        mapdl.run(f"rmodif,{rset},4,{bond_pinb}")

    # y=50 bond: vlof/vlob (top face) ↔ vlef/vleb (bottom face), x=[0, x_czm-corner]
    bond_side(RSET_BOND_BOT, y_czm_bot, x_czm - corner,
              [vlof, vlob], [vlef, vleb])

    # y=250 bond: vuuf/vuub (bottom face) ↔ vlef/vleb (top face), x=[0, x_czm-corner]
    bond_side(RSET_BOND_TOP, y_czm_top, x_czm - corner,
              [vuuf, vuub], [vlef, vleb])

    # Report
    n_total_pairs = n_dowel_pairs + 3 + 2
    mapdl.esel("s","type","",ET_TARGE); mapdl.esel("a","type","",ET_CZM_T); mapdl.esel("a","type","",ET_BOND_T)
    nt = mapdl.mesh.n_elem
    mapdl.esel("s","type","",ET_CONTA); mapdl.esel("a","type","",ET_CZM_C); mapdl.esel("a","type","",ET_BOND_C)
    nc = mapdl.mesh.n_elem
    mapdl.allsel()
    print(f"Created {n_dowel_pairs} dowel + 3 CZM + 2 bond pairs | TARGE={nt} CONTA={nc}")

    for p, label in [(RSET_CZM_BOT,"czm-shear-bot"), (RSET_CZM_TOP,"czm-shear-top"),
                     (RSET_CZM_LEFT,"czm-tension"),
                     (RSET_BOND_BOT,"bond-bot"), (RSET_BOND_TOP,"bond-top")]:
        t_et = ET_CZM_T if p <= RSET_CZM_LEFT else ET_BOND_T
        c_et = ET_CZM_C if p <= RSET_CZM_LEFT else ET_BOND_C
        mapdl.esel("s","type","",t_et); mapdl.esel("r","real","",p); nt2=mapdl.mesh.n_elem
        mapdl.esel("s","type","",c_et); mapdl.esel("r","real","",p); nc2=mapdl.mesh.n_elem
        print(f"  {label:>16} (r={p:>2}): TARGE={nt2:4d} CONTA={nc2:4d}")
    mapdl.allsel()

    return n_total_pairs


def solve(mapdl):
    plate_y1_s = 30; plate_y2_s = H - 30
    sz1_s = B/2 - t_plate/2; sz2_s = B/2 + t_plate/2

    mapdl.finish(); mapdl.run("/solu")
    mapdl.run("ANTYPE,STATIC,NEW"); mapdl.nlgeom("on"); mapdl.kbc(0)
    mapdl.nsubst(20, 200, 5); mapdl.run("AUTOTS,ON")
    mapdl.outres("all","all")
    mapdl.run("CNVTOL,F,1.0,0.01"); mapdl.run("CNVTOL,U,1.0,0.005")
    mapdl.run("NROP,UNSYM")
    mapdl.run("STABILIZE,CONSTANT,ENERGY,1e-4")

    mapdl.allsel(); mapdl.nsel("s","loc","x",-0.1,0.1)
    n_fix = mapdl.mesh.n_node
    mapdl.d("all","all",0); mapdl.allsel()
    print(f"Fixed nodes at x=0: {n_fix}")

    mapdl.nsel("s","loc","x",L-0.1,L+0.1)
    mapdl.nsel("r","loc","y",plate_y1_s,plate_y2_s)
    mapdl.nsel("r","loc","z",sz1_s,sz2_s)
    n_load = mapdl.mesh.n_node
    if n_load == 0:
        mapdl.allsel()
        mapdl.nsel("s","loc","x",L-0.1,L+0.1)
        mapdl.nsel("r","loc","y",plate_y1_s-1,plate_y2_s+1)
        mapdl.nsel("r","loc","z",sz1_s-2,sz2_s+2)
        n_load = mapdl.mesh.n_node
    mapdl.d("all","ux",imposed_disp); mapdl.d("all","uy",0); mapdl.d("all","uz",0)
    mapdl.allsel()
    print(f"Displaced nodes at plate end: {n_load}")

    print("\nCNCHECK:"); print(mapdl.run("CNCHECK"))
    print("Solving..."); mapdl.solve(); mapdl.finish()
    print("Solve complete.")


def _get_time_values(mapdl):
    """Get result set times from SET,LIST — header-aware, handles both column orders."""
    import re
    raw = mapdl.run("SET,LIST")

    # Detect which column is TIME/FREQ from the header line
    time_col = 4   # default: SET LOADSTEP SUBSTEP CUMULATIVE TIME
    for line in raw.splitlines():
        up = line.upper()
        if "SET" in up and "TIME" in up:
            parts = up.split()
            for i, p in enumerate(parts):
                if "TIME" in p:
                    time_col = i
                    break
            break

    times = []
    for line in raw.splitlines():
        nums = re.findall(r'[\d.]+(?:[Ee][+-]?\d+)?', line)
        if len(nums) > time_col:
            try:
                set_idx = float(nums[0])
                if set_idx > 0 and set_idx == int(set_idx):
                    t = float(nums[time_col])
                    if t > 0:
                        times.append(t)
            except (ValueError, IndexError):
                pass
    return sorted(times)


def postprocess(mapdl):
    mapdl.run("/POST1"); mapdl.run("INRES,ALL")
    times = _get_time_values(mapdl)
    if not times:
        print("WARNING: No result sets found.")
        return
    if len(times) >= 2 and times[-1] >= 0.999 and times[-2] < 0.99:
        times = times[:-1]
    print(f"Result sets: {len(times)}")

    forces_kN, disps_mm = [], []
    mapdl.run("SET,FIRST")
    _prev = mapdl.ignore_errors; mapdl.ignore_errors = True
    for idx, t in enumerate(times):
        mapdl.allsel(); mapdl.nsel("s","loc","x",-0.1,0.1)
        n_fixed = mapdl.mesh.n_node
        mapdl.run("NFORCE,ALL"); mapdl.run("FSUM"); mapdl.run("*GET,_FX,FSUM,,ITEM,FX")
        try:    fx = float(mapdl.parameters["_FX"])
        except: fx = 0.0
        forces_kN.append(abs(fx)/1000.0); disps_mm.append(t*imposed_disp)
        if idx < 3:
            print(f"  t={t:.4f}  ux={t*imposed_disp:.2f}mm  FX={fx/1e3:+.2f}kN  nodes@x=0:{n_fixed}")
        mapdl.allsel(); mapdl.run("SET,NEXT")
    mapdl.ignore_errors = _prev

    csv_path = "out/force_displacement_4x2_czm.csv"
    with open(csv_path,"w",newline="") as f:
        w=csv.writer(f); w.writerow(["displacement_mm","force_kN"])
        w.writerows(zip(disps_mm, forces_kN))
    print(f"Saved {csv_path}")

    peak_f = max(forces_kN) if forces_kN else 0.0
    peak_d = disps_mm[forces_kN.index(peak_f)] if forces_kN else 0.0

    fig, ax = plt.subplots(figsize=(9,6))
    ax.plot(disps_mm, forces_kN, "b-o", markersize=4, label="FEM + CZM (4x2, d=12 mm)")
    ax.axhline(F_ec5_kN, color="r", linestyle="--", linewidth=1.5,
               label=f"EC5 Rd = {F_ec5_kN:.1f} kN  (tension governs)")
    if peak_f > 0:
        ax.annotate(f"Peak {peak_f:.1f} kN\n@ {peak_d:.1f} mm",
                    xy=(peak_d, peak_f), xytext=(peak_d+0.8, peak_f*0.88),
                    arrowprops=dict(arrowstyle="->", color="navy"), color="navy", fontsize=9)
    ax.set_xlabel("Displacement [mm]", fontsize=11)
    ax.set_ylabel("Force [kN]", fontsize=11)
    ax.set_title("Block Shear — CZM Force–Displacement  (4r×2c, GL30h, d=12 mm)", fontsize=12)
    ax.legend(fontsize=10); ax.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    png = "out/force_displacement_4x2_czm.png"
    plt.savefig(png, dpi=150); print(f"Saved {png}"); plt.show()

    print(f"\nPeak FEM  : {peak_f:.1f} kN  at {peak_d:.1f} mm")
    print(f"EC5 Rd    : {F_ec5_kN:.1f} kN")
    if peak_f > 0:
        print(f"FEM/EC5   : {peak_f/F_ec5_kN:.3f}")


def main():
    os.makedirs("out", exist_ok=True)
    _clear_lock()

    print("="*62)
    print("  4x2 CZM block shear model — contact-based CZM")
    print(f"  d={d_dowel} mm  mesh={mesh_size} mm  ux={imposed_disp} mm")
    print(f"  Tension plane: sigma_max={CZM_TENSION[0]:.2f} MPa  GIc={CZM_TENSION[2]} N/mm")
    print(f"  Shear planes : tau_max  ={CZM_SHEAR[1]:.3f} MPa  GIIc={CZM_SHEAR[3]} N/mm")
    print(f"  EC5 target   : {F_ec5_kN} kN")
    print("="*62)

    mapdl = launch_mapdl(run_location="out/", override=True)

    try:
        ret = build(mapdl)
        mapdl_obj = ret[0]
        vlof, vlob, vuuf, vuub, vlef, vleb, vblf, vblb, vpl, vid_dowels = ret[1:]

        mapdl.save("pymapdl_4x2_czm_presolve", "db")
        add_contacts(mapdl, vlof, vlob, vuuf, vuub, vlef, vleb, vblf, vblb, vpl, vid_dowels)
        solve(mapdl)
        mapdl.save("pymapdl_4x2_czm_solved", "db")
        postprocess(mapdl)

    finally:
        try:   mapdl.exit()
        except: pass
        lock = "out/file.lock"
        for _ in range(20):
            if not os.path.exists(lock): break
            time.sleep(1)


if __name__ == "__main__":
    main()
