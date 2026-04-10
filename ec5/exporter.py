from pathlib import Path
from .geometry import Geometry
from .connection import FastenerSetup
from .design_values import TimberDesign


class MapdlExporter:
    """Exports a MAPDL model: timber beam + optional slotted-in steel plate."""

    def __init__(self, element_size_mm: float = 100.0):
        self.element_size_mm = element_size_mm

 
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
        return "\n".join([
            "! element type",
            f"et,{et_id},186",
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

    def _slot_and_plate(self, geo: Geometry) -> str:
        tp = geo.plate_thickness
        if tp <= 0:
            return "! no plate\n"

        B = geo.beam_width

        slot_x1 = geo.slot_x1
        slot_x2 = geo.slot_x2
        slot_y1 = geo.slot_y1
        slot_y2 = geo.slot_y2

        cY = geo.clearance_y
        plate_y1 = slot_y1 + cY / 2.0
        plate_y2 = slot_y2 - cY / 2.0

        slot_z1 = B / 2.0 - tp / 2.0
        slot_z2 = B / 2.0 + tp / 2.0

        lines = []
        lines.append("! slot and steel plate")

        lines += [
        f"block,{slot_x1},{slot_x2}, {slot_y1},{slot_y2}, {slot_z1},{slot_z2}",
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

        lines += [
            f"block,{slot_x1},{slot_x2}, {plate_y1},{plate_y2}, {slot_z1},{slot_z2}",
            "*get,vid_plate,volu,0,num,max",
            "cm,PLATE,volu,vid_plate",
            "allsel,all",
            "",
        ]

        return "\n".join(lines)



    def _plate_slots_block(self, geo: Geometry) -> str:
        tp = geo.plate_thickness
        if tp <= 0:
            return "! no plate -> no slotted holes\n"

        B = geo.beam_width
        slot_z1 = B / 2.0 - tp / 2.0
        slot_z2 = B / 2.0 + tp / 2.0

        r_plate_slot = geo.dowel_diameter / 2.0 + geo.plate_hole_clearance
        g = geo.plate_slot_clearance_y  # 1 mm
       
        lines: list[str] = []
        lines += [
            "! slotted holes in PLATE (elongated in Y only)",
            "allsel,all",
            "",
        ]

        for (x, y) in geo.dowel_positions():
            y1 = y - g
            y2 = y + g

            lines += [
                "allsel,all",
                "cmsel,s,PLATE",
                "",
                "CSYS,0",
                "WPCSYS,-1",
                f"WPOFFS,0,0,{slot_z1}",
                "WPROTA,0,0,0",
                "",
            ]

            # lower end circle tool
            lines += [
                f"CYL4,{x},{y1},{r_plate_slot},,,,{tp}",
                "*get,vtool,volu,0,num,max",
                "cmsel,s,PLATE",
                "vsbv,all,vtool",
                "cmdele,PLATE",
                "cm,PLATE,volu",
                "allsel,all",
                "vdele,vtool",
                "allsel,all",
                "",
            ]

            # upper end circle tool
            lines += [
                f"CYL4,{x},{y2},{r_plate_slot},,,,{tp}",
                "*get,vtool,volu,0,num,max",
                "cmsel,s,PLATE",
                "vsbv,all,vtool",
                "cmdele,PLATE",
                "cm,PLATE,volu",
                "allsel,all",
                "vdele,vtool",
                "allsel,all",
                "",
            ]

            # middle web tool
            lines += [
                f"block,{x-r_plate_slot},{x+r_plate_slot}, {y1},{y2}, {slot_z1},{slot_z2}",
                "*get,vtool,volu,0,num,max",
                "cmsel,s,PLATE",
                "vsbv,all,vtool",
                "cmdele,PLATE",
                "cm,PLATE,volu",
                "allsel,all",
                "vdele,vtool",
                "allsel,all",
                "",
            ]

            lines += [
                "WPOFFS,0,0,0",
                "allsel,all",
                "",
            ]

        lines += [
            "WPOFFS,0,0,0",
            "allsel,all",
            "",
        ]
        return "\n".join(lines)



    def _beam_holes_block(self, geo: Geometry) -> str:
        """
        Cut round dowel holes in the timber beam (exact dowel diameter, no clearance).
        Holes go through full beam width in Z.
        """
        if not getattr(geo, "make_beam_holes", True):
            return "! beam holes disabled\n"

        r_beam_hole = geo.dowel_diameter / 2.0 + geo.beam_hole_clearance
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
        r_dowel = geo.dowel_diameter / 2.0
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
        return "\n".join([
            "! debug: count volumes per component",

            "allsel,all",
            "cmsel,s,BEAM",
            "*get,n_beam,volu,0,count",
            "/com, BEAM selected vols = %n_beam%",
            "allsel,all",

            "cmsel,s,PLATE",
            "*get,n_plate,volu,0,count",
            "/com, PLATE selected vols = %n_plate%",
            "allsel,all",

            "cmsel,s,DOWELS",
            "*get,n_dowels,volu,0,count",
            "/com, DOWELS selected vols = %n_dowels%",
            "allsel,all",
            "",
        ])
    

    def _debug_volume_attrs_block(self, geo: Geometry) -> str:
        return "\n".join([
            "! debug volume list",
            "allsel,all",
            "vlist,all",
            "",
        ])

    def _debug_component_vlists_block(self, geo: Geometry) -> str:
        return "\n".join([
            "! debug each component separately",

            "/com, --- BEAM component ---",
            "allsel,all",
            "cmsel,s,BEAM",
            "vlist,all",

            "/com, --- PLATE component ---",
            "allsel,all",
            "cmsel,s,PLATE",
            "vlist,all",

            "/com, --- DOWELS component ---",
            "allsel,all",
            "cmsel,s,DOWELS",
            "vlist,all",

            "allsel,all",
            "",
        ])
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
    def _assign_materials(self, mat_wood: int, mat_steel: int, et_id: int) -> str:
        return "\n".join([
            "! material assignment by components (robust)",
            "",

            "! BEAM -> wood",
            "allsel,all",
            "vsel,none",
            "cmsel,a,BEAM",
            f"vatt,{mat_wood},,{et_id}",
            "allsel,all",
            "",

            "! PLATE -> steel",
            "allsel,all",
            "vsel,none",
            "cmsel,a,PLATE",
            f"vatt,{mat_steel},,{et_id}",
            "allsel,all",
            "",

            "! DOWELS -> steel",
            "allsel,all",
            "vsel,none",
            "cmsel,a,DOWELS",
            f"vatt,{mat_steel},,{et_id}",
            "allsel,all",
            "",
        ])

    # -------------------------------------------------------------------------
    # MESH
    # -------------------------------------------------------------------------
    def _mesh_block(self) -> str:
        h = self.element_size_mm
        return "\n".join([
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

            "! mesh PLATE",
            "cmsel,s,PLATE",
            "vmesh,all",
            "allsel,all",
            "",

            "! mesh DOWELS",
            "cmsel,s,DOWELS",
            "vmesh,all",
            "allsel,all",
            "",

            "*get,nn,node,0,count",
            "*get,ne,elem,0,count",
            "/com, NODE=%nn%  ELEM=%ne%",
            "",
        ])


    def _finish_block(self) -> str:
        return "\n".join([
            "allsel,all",
            "finish",
            "",
        ])
    
    def _contact_block_frictionless(self, geo: Geometry) -> str:
        """
        Create frictionless contact after meshing:
        - target on each steel dowel outer surface
        - contact on timber hole surface near each dowel
        - contact on plate slot surface near each dowel

        This is a practical APDL-generated contact setup for the current geometry.
        """

        search_dx = max(geo.dowel_diameter, 10.0)
        search_dy = max(geo.dowel_diameter, 10.0)

        lines: list[str] = []
        lines += [
            "! ---------------- CONTACT DEFINITION ----------------",
            "! frictionless contact: dowel <-> beam and dowel <-> plate",
            "allsel,all",
            "",
            "! contact element types",
            "et,2,targe170",
            "et,3,conta174",
            "",
            "! basic contact options",
            "keyopt,3,4,0",
            "keyopt,3,12,0",
            "",
            "! real constant sets",
            "r,1",
            "r,2",
            "r,3",
            "r,4",
            "",
        ]

        for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
            lines += [
                f"! ---- CONTACT SET FOR DOWEL {i} at x={x}, y={y} ----",
                "",
                "! target on dowel surface",
                "allsel,all",
                f"cmsel,s,DOWEL{i}",
                "nslv,s,1",
                "esln,s",
                "type,2",
                f"real,{i}",
                "mat,2",
                "esurf",
                "allsel,all",
                "",
                "! contact on timber hole region",
                "allsel,all",
                "cmsel,s,BEAM",
                "nsle,s",
                f"nsel,r,loc,x,{x-search_dx},{x+search_dx}",
                f"nsel,r,loc,y,{y-search_dy},{y+search_dy}",
                f"nsel,r,loc,z,0,{geo.beam_width}",
                "esln,s",
                "type,3",
                f"real,{i}",
                "mat,1",
                "esurf",
                "allsel,all",
                "",
            ]

            if geo.plate_thickness > 0:
                slot_z1 = geo.beam_width / 2.0 - geo.plate_thickness / 2.0
                slot_z2 = geo.beam_width / 2.0 + geo.plate_thickness / 2.0
                plate_y1 = geo.slot_y1 + geo.clearance_y / 2.0
                plate_y2 = geo.slot_y2 - geo.clearance_y / 2.0

                lines += [
                    "! contact on plate slot region",
                    "allsel,all",
                    "cmsel,s,PLATE",
                    "nsle,s",
                    f"nsel,r,loc,x,{x-search_dx},{x+search_dx}",
                    f"nsel,r,loc,y,{plate_y1},{plate_y2}",
                    f"nsel,r,loc,z,{slot_z1},{slot_z2}",
                    "esln,s",
                    "type,3",
                    f"real,{i}",
                    "mat,2",
                    "esurf",
                    "allsel,all",
                    "",
                ]

        lines += [
            "! ----------------------------------------------------",
            "allsel,all",
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
    ) -> None:

        mat_wood = 1
        mat_steel = 2
        et_id = 1

        blocks: list[str] = []
        blocks.append(self._material_block_wood(mat_wood, timber))
        blocks.append(self._material_block_steel(mat_steel))
        blocks.append(self._element_block(et_id))
        blocks.append(self._beam_block(geo))
        blocks.append(self._slot_and_plate(geo))
        blocks.append(self._beam_holes_block(geo)) 
        blocks.append(self._plate_slots_block(geo)) 
        blocks.append(self._dowels_block(geo))
        blocks.append(self._dowels_component_block(geo))
        #blocks.append(self._rebuild_final_beam_block())
        blocks.append(self._check_components_block(geo))
        blocks.append(self._assign_materials(mat_wood, mat_steel, et_id))
        blocks.append(self._debug_component_vlists_block(geo))
        blocks.append(self._debug_volume_attrs_block(geo))
        blocks.append(self._mesh_block())
        blocks.append(self._contact_block_frictionless(geo))
        blocks.append(self._finish_block())
        #blocks.append(self._bonded_contact_block_v1(geo))
        
    

        Path(path).write_text("\n".join(blocks))

