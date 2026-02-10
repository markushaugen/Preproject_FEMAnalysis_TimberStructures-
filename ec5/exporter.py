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
            f"mp,ex,{mat_id},210e9",
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

        L = geo.beam_length
        H = geo.beam_height
        B = geo.beam_width

        slot_x1 = geo.slot_x1
        slot_x2 = geo.slot_x2
        slot_y1 = geo.slot_y1
        slot_y2 = geo.slot_y2

        cY = geo.clearance_y
        plate_y1 = slot_y1 + cY/2.0
        plate_y2 = slot_y2 - cY/2.0

        # Plate thickness centered in Z (beam width)
        slot_z1 = B/2.0 - tp/2.0
        slot_z2 = B/2.0 + tp/2.0

        lines = []
        lines.append("! slot and steel plate")

        # slot tool volume
        lines += [
            "! create slot volume",
            f"block,{slot_x1},{slot_x2}, {slot_y1},{slot_y2}, {slot_z1},{slot_z2}",
            "*get,vid_slot,volu,0,num,max",
            "",
            "! subtract slot from BEAM",
            "cmsel,s,BEAM",
            "vsbv,all,vid_slot",
            "allsel,all",
            "vdele,vid_slot",
            "nummrg,all",
            "",
        ]

        # plate volume (same X,Z but reduced Y to create clearance)
        lines += [
            "! create steel plate volume",
            f"block,{slot_x1},{slot_x2}, {plate_y1},{plate_y2}, {slot_z1},{slot_z2}",
            "*get,vid_plate,volu,0,num,max",
            "cm,PLATE,volu,vid_plate",
            "allsel,all",
            "",
        ]

        return "\n".join(lines)

    

    #Dowels
    def _dowels_block(self, geo: Geometry) -> str:
        """Create dowel volumes using CYL4. Stores them in component DOWELS."""
        r = geo.dowel_diameter / 2.0
        B = geo.beam_width  # depth in Z-direction

        lines: list[str] = []
        lines.append("! dowels")
        lines.append("! CYL4 is used with WP reset for robustness")
        lines.append("cmdele,DOWELS")  # safe if not existing in some versions; ok if ignored
        lines.append("")

        for i, (x, y) in enumerate(geo.dowel_positions(), start=1):
            lines.extend([
                "CSYS,0",
                "WPCSYS,-1",
                "WPOFFS,0,0,0",
                "WPROTA,0,0,0",
                f"CYL4,{x},{y},{r},,,,{B}",
                f"*get,vid_dowel_{i},volu,0,num,max",
                f"cm,DOWELS,volu,vid_dowel_{i}",
                "allsel,all",
                "",
            ])

        return "\n".join(lines)


    # MATERIAL ASSIGNMENT
    def _assign_materials(self, mat_wood: int, mat_steel: int, et_id: int) -> str:
        """
        First give all volumes wood (MAT=mat_wood),
        then override PLATE component to steel (MAT=mat_steel).
        """
        return "\n".join([
            "! material assignment: all wood, plate overridden to steel",
            f"type,{et_id}",
            "vsel,all",
            f"vatt,{mat_wood},,{et_id}",
            "",
            "cmsel,s,PLATE",
            f"vatt,{mat_steel},,{et_id}",
            "",
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
            f"esize,{h}",
            "vsel,all",
            "vmesh,all",
            "allsel,all",
            "finish",
            "",
        ])


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
        blocks.append(self._dowels_block(geo))
        blocks.append(self._assign_materials(mat_wood, mat_steel, et_id))
        blocks.append(self._mesh_block())

        Path(path).write_text("\n".join(blocks))

