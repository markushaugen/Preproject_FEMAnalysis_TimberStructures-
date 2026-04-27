from pathlib import Path
from .geometry import Geometry
from .connection import FastenerSetup
from .design_values import TimberDesign


class MapdlExporter:
    """Exports a MAPDL model: timber beam + optional slotted-in steel plate."""

    def __init__(self, element_size_mm: float = 100.0, block_shear: bool = False):
        self.element_size_mm = element_size_mm
        self.block_shear = block_shear

    def _dowel_r(self, geo: Geometry) -> float:
        """Rendered dowel radius. Doubled when block_shear=True to force timber failure."""
        return geo.dowel_diameter if self.block_shear else geo.dowel_diameter / 2.0

    def _hole_r(self, geo: Geometry) -> float:
        """Beam hole radius. No clearance in block_shear mode."""
        if self.block_shear:
            return geo.dowel_diameter  # 2× nominal, zero clearance
        return geo.dowel_diameter / 2.0 + geo.beam_hole_clearance

    def _slot_r(self, geo: Geometry) -> float:
        """Plate slot hole radius."""
        if self.block_shear:
            return geo.dowel_diameter  # 2× nominal
        return geo.dowel_diameter / 2.0 + geo.plate_hole_clearance

 
    # MATERIALS
    def _material_block_wood(self, mat_id: int, timber: TimberDesign) -> str:
        e = timber.elastic
        return "\n".join([
            "/PREP7",
            "! timber material",
            f"mp,ex,{mat_id},{e.EX}",
            f"mp,ey,{mat_id},{e.EY}",
            f"mp,ez,{mat_id},{e.EZ}",
            f"mp,prxy,{mat_id},{e.PRXY}",
            f"mp,pryz,{mat_id},{e.PRYZ}",
            f"mp,prxz,{mat_id},{e.PRXZ}",
            f"mp,gxy,{mat_id},{e.GXY}",
            f"mp,gyz,{mat_id},{e.GYZ}",
            f"mp,gxz,{mat_id},{e.GXZ}",
            "",
        ])

    def _material_block_steel(self, mat_id: int) -> str:
        return "\n".join([
            "! steel material",
            f"mp,ex,{mat_id},210000",
            f"mp,prxy,{mat_id},0.3",
            "",
        ])


    # ELEMENT TYPE
    def _element_block(self, et_id: int = 1) -> str:
        # SOLID187: 10-node quadratic tet - handles curved/complex geometry
        # much better than SOLID186 (20-node hex) for cylindrical holes and
        # dowels. Avoids the "mid-node straightening" warning.
        return "\n".join([
            "! element type: SOLID187 (10-node tet, better for curved geometry)",
            f"et,{et_id},187",
            "",
        ])


    # GEOMETRY
    def _beam_block(self, geo: Geometry) -> str:
        """Create main beam volume and store it in component BEAM."""
        L = geo.beam_length
        B = geo.beam_width
        H = geo.beam_height

        return "\n".join([
            "! timber beam volume",
            f"block,0,{L}, 0,{H}, 0,{B}",
            "*get,vid_beam,volu,0,num,max",
            "cm,BEAM,volu,vid_beam",
            "allsel,all",
            "",
        ])

    def _beam_slots_and_plates(self, geo: Geometry) -> str:
        """Cut one slot per plate from BEAM, then create each PLATEk volume."""
        tp = geo.plate_thickness
        if tp <= 0:
            return "! no plate\n"

        slot_x1, slot_x2 = geo.plate_extents()
        slot_y1 = geo.slot_y1
        slot_y2 = geo.slot_y2
        cY = geo.clearance_y
        plate_y1 = slot_y1 + cY / 2.0
        plate_y2 = slot_y2 - cY / 2.0
        z_centers = geo.plate_z_centers()

        lines = ["! beam slots and steel plates"]

        # Cut all slots from BEAM first so plate volumes don't exist yet during boolean ops
        for k, zc in enumerate(z_centers, 1):
            sz1 = zc - tp / 2.0
            sz2 = zc + tp / 2.0
            lines += [
                f"! Cut slot {k} from BEAM (z = {sz1:.3f} to {sz2:.3f})",
                f"block,{slot_x1},{slot_x2}, {slot_y1},{slot_y2}, {sz1},{sz2}",
                "*get,vid_slot,volu,0,num,max",
                "cmsel,s,BEAM",
                "vsbv,all,vid_slot",
                "cmdele,BEAM",
                "cm,BEAM,volu",
                "allsel,all",
                "vdele,vid_slot",
                "allsel,all",
                "",
            ]

        # Create each plate volume
        for k, zc in enumerate(z_centers, 1):
            sz1 = zc - tp / 2.0
            sz2 = zc + tp / 2.0
            lines += [
                f"! Create PLATE{k} (z = {sz1:.3f} to {sz2:.3f})",
                f"block,{slot_x1},{slot_x2}, {plate_y1},{plate_y2}, {sz1},{sz2}",
                "*get,vid_plate,volu,0,num,max",
                f"cm,PLATE{k},volu,vid_plate",
                "allsel,all",
                "",
            ]

        return "\n".join(lines)



    def _plate_slots_block(self, geo: Geometry) -> str:
        tp = geo.plate_thickness
        if tp <= 0:
            return "! no plate -> no slotted holes\n"

        r_slot = self._slot_r(geo)
        g = geo.plate_slot_clearance_y
        z_centers = geo.plate_z_centers()

        lines: list[str] = ["! slotted holes in plate(s) (elongated in Y only)", "allsel,all", ""]

        for k, zc in enumerate(z_centers, 1):
            comp = f"PLATE{k}"
            sz1 = zc - tp / 2.0
            sz2 = zc + tp / 2.0

            lines += [f"! Slots in {comp}", ""]

            for (x, y) in geo.dowel_positions():
                y1 = y - g
                y2 = y + g

                lines += [
                    "allsel,all",
                    f"cmsel,s,{comp}",
                    "",
                    "CSYS,0",
                    "WPCSYS,-1",
                    f"WPOFFS,0,0,{sz1}",
                    "WPROTA,0,0,0",
                    "",
                    f"CYL4,{x},{y1},{r_slot},,,,{tp}",
                    "*get,vtool,volu,0,num,max",
                    f"cmsel,s,{comp}",
                    "vsbv,all,vtool",
                    f"cmdele,{comp}",
                    f"cm,{comp},volu",
                    "allsel,all",
                    "vdele,vtool",
                    "allsel,all",
                    "",
                    f"CYL4,{x},{y2},{r_slot},,,,{tp}",
                    "*get,vtool,volu,0,num,max",
                    f"cmsel,s,{comp}",
                    "vsbv,all,vtool",
                    f"cmdele,{comp}",
                    f"cm,{comp},volu",
                    "allsel,all",
                    "vdele,vtool",
                    "allsel,all",
                    "",
                    f"block,{x-r_slot},{x+r_slot}, {y1},{y2}, {sz1},{sz2}",
                    "*get,vtool,volu,0,num,max",
                    f"cmsel,s,{comp}",
                    "vsbv,all,vtool",
                    f"cmdele,{comp}",
                    f"cm,{comp},volu",
                    "allsel,all",
                    "vdele,vtool",
                    "allsel,all",
                    "",
                    "WPOFFS,0,0,0",
                    "allsel,all",
                    "",
                ]

        lines += ["WPOFFS,0,0,0", "allsel,all", ""]
        return "\n".join(lines)



    def _beam_holes_block(self, geo: Geometry) -> str:
        """
        Cut round dowel holes in the timber beam (exact dowel diameter, no clearance).
        Holes go through full beam width in Z.
        """
        if not getattr(geo, "make_beam_holes", True):
            return "! beam holes disabled\n"

        r_beam_hole = self._hole_r(geo)
        B = geo.beam_width  # through-thickness in Z

        lines: list[str] = []
        lines += [
            "! round holes in BEAM for dowels (exact diameter)",
            "allsel,all",
            "",
        ]

        for x, y in geo.dowel_positions():
            lines += [
                "CSYS,0",
                "WPCSYS,-1",
                "WPOFFS,0,0,0",
                "WPROTA,0,0,0",
                "",
                f"CYL4,{x},{y},{r_beam_hole},,,,{B}",
                "*get,vhole,volu,0,num,max",
                "",
                "cmsel,s,BEAM",
                "vsbv,all,vhole",
                "cmdele,BEAM",
                "cm,BEAM,volu",
                "allsel,all",
                "vdele,vhole",
                "allsel,all",
                "",
            ]


        # for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
        #     lines += [
        #     "CSYS,0",
        #     "WPCSYS,-1",
        #     "WPOFFS,0,0,0",
        #     "WPROTA,0,0,0",
        #     "",
        #     f"CYL4,{x},{y},{r_beam_hole},,,,{B}",
        #     "*get,vhole,volu,0,num,max",
        #     "",
        #     "cmsel,s,BEAM",
        #     "vsbv,all,vhole",
        #     "cmdele,BEAM",
        #     "cm,BEAM,volu",
        #     "allsel,all",
        #     "vdele,vhole",
        #     "allsel,all",
        #     "",
        # ]
        return "\n".join(lines)



    #Dowels
    def _dowels_block(self, geo: Geometry) -> str:
        """Create dowel volumes using CYL4. Stores them in component DOWELS."""
        r_dowel = self._dowel_r(geo)
        B = geo.beam_width  # depth in Z-direction

        lines: list[str] = []
        lines.append("! dowels")
        lines.append("! CYL4 is used with WP reset for robustness")
        lines.append("cmdele,DOWELS")
        lines.append("")

        for i in range(1, geo.num_dowels + 1):
            lines.append(f"cmdele,DOWEL{i}")
        lines.append("")

        for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
            lines.extend([
                "allsel,all",
                "csys,0",
                "wpcsys,0",
                "wpoffs,0,0,0",
                "",
                f"cyl4,{x},{y},{r_dowel},,,0,{B}",
                "*get,vid_dowel,volu,0,num,max",
                f"cm,DOWEL{i},volu,vid_dowel",
                "",
                "allsel,all",
                "",
            ])

        return "\n".join(lines)

    def _dowels_component_block(self, geo: Geometry) -> str:
        """Build DOWELS component robustly from DOWEL1...DOWELn"""
        lines = []
        lines.append("! build DOWELS component from individual dowels")
        lines.append("cmdele,DOWELS")

        for i in range(1, geo.num_dowels + 1):
            if i == 1:
                lines.append(f"cmsel,s,DOWEL{i}")
            else:
                lines.append(f"cmsel,a,DOWEL{i}")

        lines += [
            "cm,DOWELS,volu",
            "allsel,all",
            "",
        ]

        return "\n".join(lines)
    
    # def _rebuild_final_beam_block(self) -> str:
    #     return "\n".join([
    #         "! rebuild BEAM as all volumes except PLATE and DOWELS",
    #         "allsel,all",
    #         "vsel,all",
    #         "cmsel,u,PLATE",
    #         "cmsel,u,DOWELS",
    #         "cmdele,BEAM",
    #         "cm,BEAM,volu",
    #         "allsel,all",
    #         "",
    #     ])
    
    def _check_components_block(self, geo: Geometry) -> str:
        lines = [
            "! debug: count volumes per component",
            "allsel,all",
            "cmsel,s,BEAM",
            "*get,n_beam,volu,0,count",
            "/com, BEAM selected vols = %n_beam%",
            "allsel,all",
        ]
        for k in range(1, geo.n_plates + 1):
            lines += [
                f"cmsel,s,PLATE{k}",
                f"*get,n_plate{k},volu,0,count",
                f"/com, PLATE{k} selected vols = %n_plate{k}%",
                "allsel,all",
            ]
        lines += [
            "cmsel,s,DOWELS",
            "*get,n_dowels,volu,0,count",
            "/com, DOWELS selected vols = %n_dowels%",
            "allsel,all",
            "",
        ]
        return "\n".join(lines)
    

    def _debug_volume_attrs_block(self, geo: Geometry) -> str:
        return "\n".join([
            "! debug volume list",
            "allsel,all",
            "vlist,all",
            "",
        ])

    def _debug_component_vlists_block(self, geo: Geometry) -> str:
        lines = [
            "! debug each component separately",
            "/com, --- BEAM component ---",
            "allsel,all",
            "cmsel,s,BEAM",
            "vlist,all",
        ]
        for k in range(1, geo.n_plates + 1):
            lines += [
                f"/com, --- PLATE{k} component ---",
                "allsel,all",
                f"cmsel,s,PLATE{k}",
                "vlist,all",
            ]
        lines += [
            "/com, --- DOWELS component ---",
            "allsel,all",
            "cmsel,s,DOWELS",
            "vlist,all",
            "allsel,all",
            "",
        ]
        return "\n".join(lines)
        # def _bonded_contact_block_v1(self, geo: Geometry) -> str:
    #     """
    #     Bonded contact (v1):
    #     - Plate <-> Beam at slot Z faces
    #     - Each Dowel <-> Beam hole at cylindrical surface
    #     Assumes:
    #     volu 1=BEAM, 2=PLATE, 3-6=DOWELS (your verified IDs)
    #     components BEAM, PLATE, DOWEL1..DOWELn exist
    #     """
        # tp = geo.plate_thickness
        # B = geo.beam_width
        # slot_z1 = B / 2.0 - tp / 2.0
        # slot_z2 = B / 2.0 + tp / 2.0

        # # Radii (must match what you used in geometry blocks)
        # r_dowel = geo.dowel_diameter / 2.0
        # r_beam_hole = geo.dowel_diameter / 2.0 + getattr(geo, "beam_hole_clearance", 0.0)

        # # Tolerance for node selection on radius (mm)
        # tol = max(0.2, 0.3 * self.element_size_mm)

        # lines: list[str] = []
        # lines += [
        #     "/prep7",
        #     "! ---------------- CONTACT (BONDED v1) ----------------",
        #     "allsel,all",
        #     "",
        #     "! Contact element types",
        #     "et,10,170      ! TARGE170",
        #     "et,11,174      ! CONTA174",
        #     "! Bonded contact (MPC-style bonded).",
        #     "keyopt,11,12,5",
        #     "keyopt,11,4,0",
        #     "",
        #     "! Real constants set (defaults are ok for bonded, but keep a set id)",
        #     "r,11",
        #     "",
        # ]

        # # --- A) PLATE <-> BEAM on slot Z faces (two sides) ---
        # # Target on PLATE (stiffer), Contact on BEAM
        # for z in (slot_z1, slot_z2):
        #     lines += [
        #         f"! Plate-Beam bonded at z={z}",
        #         "allsel,all",
        #         "",
        #         "! TARGET on PLATE face",
        #         "cmsel,s,PLATE",
        #         "nsla,s,1",
        #         f"nsel,r,loc,z,{z}",
        #         f"nsel,r,loc,x,{geo.slot_x1},{geo.slot_x2}",
        #         f"nsel,r,loc,y,{geo.slot_y1},{geo.slot_y2}",
        #         "type,10",
        #         "real,11",
        #         "esurf",
        #         "",
        #         "! CONTACT on BEAM face",
        #         "allsel,all",
        #         "cmsel,s,BEAM",
        #         "nsla,s,1",
        #         f"nsel,r,loc,z,{z}",
        #         f"nsel,r,loc,x,{geo.slot_x1},{geo.slot_x2}",
        #         f"nsel,r,loc,y,{geo.slot_y1},{geo.slot_y2}",
        #         "type,11",
        #         "real,11",
        #         "esurf",
        #         "allsel,all",
        #         "",
        #     ]

        # # --- B) Each DOWEL <-> BEAM hole on cylindrical surface ---
        # # Target on DOWEL (steel), Contact on BEAM hole surface
        # for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
        #     lines += [
        #         f"! Dowel {i} bonded to BEAM hole (cylindrical selection)",
        #         "allsel,all",
        #         "",
        #         f"! Local cylindrical CSYS around dowel center (x={x}, y={y})",
        #         f"local,100,1,{x},{y},0",
        #         "csys,100",
        #         "",
        #         "! TARGET on DOWEL surface (R = r_dowel)",
        #         f"cmsel,s,DOWEL{i}",
        #         "nsla,s,1",
        #         f"nsel,r,loc,x,{r_dowel - tol},{r_dowel + tol}",
        #         "type,10",
        #         "real,11",
        #         "esurf",
        #         "",
        #         "! CONTACT on BEAM hole surface (R = r_beam_hole)",
        #         "allsel,all",
        #         "cmsel,s,BEAM",
        #         "nsla,s,1",
        #         f"nsel,r,loc,x,{r_beam_hole - tol},{r_beam_hole + tol}",
        #         "type,11",
        #         "real,11",
        #         "esurf",
        #         "",
        #         "csys,0",
        #         "allsel,all",
        #         "",
        #     ]

        # lines += [
        #     "! -----------------------------------------------------",
        #     "allsel,all",
        #     "",
        # ]
        # return "\n".join(lines)

    # MATERIAL ASSIGNMENT
    def _assign_materials_pre(self, mat_wood: int, mat_steel: int, et_id: int) -> str:
        """Pre-mesh vatt hints — sets default attributes on volumes before meshing."""
        return "\n".join([
            "! ---- pre-mesh volume attribute hints (vatt) ----",
            "! These set the default, but emodif after meshing is authoritative.",
            "",
            "allsel,all",
            f"vatt,{mat_steel},,{et_id}",
            "",
            "cmsel,s,BEAM",
            f"vatt,{mat_wood},,{et_id}",
            "allsel,all",
            "",
        ])

    def _assign_materials_post(self, mat_wood: int, mat_steel: int, geo: Geometry) -> str:
        """Post-mesh emodif — reliable material assignment by component."""
        lines = [
            "! ---- post-mesh material assignment (emodif) ----",
            "",
            "! BEAM -> timber (mat 1)",
            "allsel,all",
            "cmsel,s,BEAM",
            "esla,s",
            f"emodif,all,mat,{mat_wood}",
            "allsel,all",
            "",
        ]
        for k in range(1, geo.n_plates + 1):
            lines += [
                f"! PLATE{k} -> steel (mat {mat_steel})",
                "allsel,all",
                f"cmsel,s,PLATE{k}",
                "esla,s",
                f"emodif,all,mat,{mat_steel}",
                "allsel,all",
                "",
            ]
        lines += [
            "! DOWELS -> steel (mat 2)",
            "allsel,all",
            "cmsel,s,DOWELS",
            "esla,s",
            f"emodif,all,mat,{mat_steel}",
            "allsel,all",
            "",
        ]
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # MESH
    # -------------------------------------------------------------------------
    def _local_refinement_block(self, geo: Geometry) -> str:
        """Apply LESIZE = esize/4 on lines around each dowel hole before meshing."""
        fine = self.element_size_mm / 4.0
        r   = self._hole_r(geo)
        tol = max(2.0, self.element_size_mm * 0.4)

        lines = [
            f"! Local mesh refinement around dowel holes (LESIZE = {fine:.1f} mm)",
            "allsel,all",
            "",
        ]

        for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
            lines += [
                f"! Dowel {i}  x={x}  y={y}",
                f"LSEL,S,LOC,X,{x - r - tol:.2f},{x + r + tol:.2f}",
                f"LSEL,R,LOC,Y,{y - r - tol:.2f},{y + r + tol:.2f}",
                f"LESIZE,ALL,{fine:.2f}",
                "ALLSEL,ALL",
                "",
            ]

        return "\n".join(lines)

    def _mesh_block(self, geo: Geometry) -> str:
        h = self.element_size_mm
        lines = [
            "! meshing",
            "mshape,1,3d",
            "mshkey,0",
            f"esize,{h}",
            "",
            "! mesh BEAM",
            "cmsel,s,BEAM",
            "vmesh,all",
            "allsel,all",
            "",
        ]
        for k in range(1, geo.n_plates + 1):
            lines += [
                f"! mesh PLATE{k}",
                f"cmsel,s,PLATE{k}",
                "vmesh,all",
                "allsel,all",
                "",
            ]
        lines += [
            "! mesh DOWELS",
            "cmsel,s,DOWELS",
            "vmesh,all",
            "allsel,all",
            "",
            "*get,nn,node,0,count",
            "*get,ne,elem,0,count",
            "/com, NODE=%nn%  ELEM=%ne%",
            "",
        ]
        return "\n".join(lines)


    def _finish_block(self) -> str:
        return "\n".join([
            "allsel,all",
            "finish",
            "",
        ])
    
    def _contact_block_bonded(self, geo: Geometry) -> str:
        """
        Frictional contact (Augmented Lagrangian).

        mat 3: steel-on-timber (mu=0.3)
        mat 4: steel-on-steel  (mu=0.15)

        For each dowel i:
          - 1 beam pair   (dowel <-> beam hole, full Z)
          - n_plates plate pairs  (dowel <-> PLATEk slot, restricted Z per plate)

        Total real sets = num_dowels * (1 + n_plates).
        """
        r   = self._dowel_r(geo)
        tol = max(2.0, self.element_size_mm * 0.6)
        tp  = geo.plate_thickness
        z_centers = geo.plate_z_centers()
        n_pairs = geo.num_dowels * (1 + geo.n_plates)

        lines: list[str] = [
            "! ============================================================",
            "! FRICTIONAL CONTACT - Augmented Lagrangian",
            f"! mat 3: steel-on-timber (mu=0.3)  mat 4: steel-on-steel (mu=0.15)",
            f"! {geo.num_dowels} dowels x (1 beam pair + {geo.n_plates} plate pair(s))"
            f" = {n_pairs} real sets",
            "! ============================================================",
            "/prep7",
            "allsel,all",
            "",
            "! friction contact materials",
            "mp,mu,3,0.3",
            "mp,mu,4,0.15",
            "",
            "et,2,targe170",
            "et,3,conta174",
            "",
            "! Augmented Lagrangian (keyopt 2=0): avoids MPC self-contact issue",
            "keyopt,3,2,0",
            "! Standard frictional contact (keyopt 12=0)",
            "keyopt,3,12,0",
            "! Ignore initial gap/penetration -> prevents initial offset errors",
            "keyopt,3,9,1",
            "",
        ]

        for rset in range(1, n_pairs + 1):
            lines.append(f"r,{rset}")
        lines.append("")

        pair_counter = 0
        for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
            pair_counter += 1
            pair_beam = pair_counter

            lines += [
                f"! ---- DOWEL {i}  x={x}  y={y} ----",
                f"! Pair {pair_beam}: dowel {i} -> beam hole (mu=0.3)",
                "",
                "! TARGET: dowel cylindrical surface (full Z)",
                "allsel,all",
                f"cmsel,s,DOWEL{i}",
                "nslv,s,1",
                f"nsel,r,loc,x,{x - r - tol},{x + r + tol}",
                f"nsel,r,loc,y,{y - r - tol},{y + r + tol}",
                "type,2",
                f"real,{pair_beam}",
                "mat,2",
                "esurf",
                "allsel,all",
                "",
                "! CONTACT: timber hole surface (mat 3, mu=0.3)",
                "allsel,all",
                "cmsel,s,BEAM",
                "nslv,s,1",
                f"nsel,r,loc,x,{x - r - tol},{x + r + tol}",
                f"nsel,r,loc,y,{y - r - tol},{y + r + tol}",
                f"nsel,r,loc,z,0,{geo.beam_width}",
                "type,3",
                f"real,{pair_beam}",
                "mat,3",
                "esurf",
                "allsel,all",
                "",
            ]

            if tp > 0:
                for k, zc in enumerate(z_centers, 1):
                    pair_counter += 1
                    pair_plate = pair_counter
                    sz1 = zc - tp / 2.0
                    sz2 = zc + tp / 2.0

                    lines += [
                        f"! Pair {pair_plate}: dowel {i} -> PLATE{k} slot (mu=0.15)",
                        "",
                        f"! TARGET: dowel {i} nodes in PLATE{k} Z-zone",
                        "allsel,all",
                        f"cmsel,s,DOWEL{i}",
                        "nslv,s,1",
                        f"nsel,r,loc,x,{x - r - tol},{x + r + tol}",
                        f"nsel,r,loc,y,{y - r - tol},{y + r + tol}",
                        f"nsel,r,loc,z,{sz1},{sz2}",
                        "type,2",
                        f"real,{pair_plate}",
                        "mat,2",
                        "esurf",
                        "allsel,all",
                        "",
                        f"! CONTACT: PLATE{k} slot nodes (mat 4, mu=0.15)",
                        "allsel,all",
                        f"cmsel,s,PLATE{k}",
                        "nslv,s,1",
                        f"nsel,r,loc,x,{x - r - tol},{x + r + tol}",
                        f"nsel,r,loc,y,{y - r - tol},{y + r + tol}",
                        f"nsel,r,loc,z,{sz1},{sz2}",
                        "type,3",
                        f"real,{pair_plate}",
                        "mat,4",
                        "esurf",
                        "allsel,all",
                        "",
                    ]

        lines += [
            "! ============================================================",
            "allsel,all",
            "",
            "! PINB = 10 mm for all contact pairs (field 4 of CONTA174 real constants).",
            "! Prevents missed contact from curved-surface facet gaps (~1 mm at 10 mm mesh).",
            f"*do,ipinb,1,{n_pairs}",
            "rmodif,ipinb,4,10.0",
            "*enddo",
            "allsel,all",
            "",
        ]
        return "\n".join(lines)

    def _solution_block(self, geo: Geometry, imposed_disp_mm: float = 20.0) -> str:
        """
        Static solution with imposed displacement applied to all PLATEk end faces.

        Boundary conditions:
          x=0 : UX=UY=UZ=0  (fixed timber support)
          x=L : UX=imposed, UY=0, UZ=0 on each PLATEk end face
        """
        L   = geo.beam_length
        tol = max(1.0, self.element_size_mm * 0.5)

        lines = [
            "! ============================================================",
            "! SOLUTION",
            "! ============================================================",
            "finish",
            "/solu",
            "antype,static",
            "",
            "! Fixed support: lock all DOF on the timber left face (x=0)",
            f"nsel,s,loc,x,0,{tol}",
            "d,all,all,0",
            "allsel,all",
            "",
            "! Loaded end: impose displacement on all plate end faces (x=L)",
        ]
        for k in range(1, geo.n_plates + 1):
            lines += [
                f"cmsel,s,PLATE{k}",
                "nslv,s,1",
                f"nsel,r,loc,x,{L - tol},{L + tol}",
                f"d,all,ux,{imposed_disp_mm}",
                "d,all,uy,0",
                "d,all,uz,0",
                "allsel,all",
                "",
            ]
        lines += [
            "! Nonlinear geometry on - required for frictional contact",
            "nlgeom,on",
            "nsubst,10,50,5",
            "cnvtol,f,,0.01",
            "outres,all,last",
            "",
            "solve",
            "finish",
            "",
            "! ============================================================",
            "! POST-PROCESSING: open manually in ANSYS GUI after solve",
            "! General Postproc -> Plot Results -> Contour Plot -> Nodal Solu",
            "! ============================================================",
            "/post1",
            "set,last",
            "finish",
            "",
        ]
        return "\n".join(lines)

    # EXPORT
    def export_mapdl_model(
        self,
        path: str,
        timber: TimberDesign,
        geo: Geometry,
        setup: FastenerSetup | None = None,
        model_name: str = "timber_model",
        imposed_disp_mm: float = 20.0,
        solve: bool = True,
        working_dir: str | None = None,
    ) -> None:
        """
        Export a complete MAPDL .mac file:
          /PREP7  -> geometry -> mesh -> bonded contact
          /SOLU   -> BC + imposed displacement -> solve
          /POST1  -> basic plots

        Priority 1: get a simulation running with bonded MPC contact.
        Switch to frictional contact once this baseline works.

        Parameters
        ----------
        imposed_disp_mm : float
            Displacement applied at x=beam_length in X-direction (mm).
            Negative = pulling away from support (tension). Default -2 mm.
        """

        mat_wood = 1
        mat_steel = 2
        et_id = 1

        blocks: list[str] = []
        if working_dir:
            blocks.append(f"/CWD,'{working_dir}'\n")
        blocks.append(self._material_block_wood(mat_wood, timber))
        blocks.append(self._material_block_steel(mat_steel))
        blocks.append(self._element_block(et_id))
        blocks.append(self._beam_block(geo))
        blocks.append(self._beam_slots_and_plates(geo))
        blocks.append(self._beam_holes_block(geo))
        blocks.append(self._plate_slots_block(geo))
        blocks.append(self._dowels_block(geo))
        blocks.append(self._dowels_component_block(geo))
        blocks.append(self._check_components_block(geo))
        blocks.append(self._assign_materials_pre(mat_wood, mat_steel, et_id))
        blocks.append(self._debug_component_vlists_block(geo))
        blocks.append(self._debug_volume_attrs_block(geo))
        blocks.append(self._local_refinement_block(geo))
        blocks.append(self._mesh_block(geo))
        blocks.append(self._assign_materials_post(mat_wood, mat_steel, geo))
        blocks.append(self._contact_block_bonded(geo))
        if solve:
            blocks.append(self._solution_block(geo, imposed_disp_mm))

        Path(path).write_text("\n".join(blocks))

