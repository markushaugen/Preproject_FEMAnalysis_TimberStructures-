# ec5/exporter.py
from pathlib import Path
from .geometry import Geometry
from .connection import FastenerSetup
from .design_values import TimberDesign


class MapdlExporter:
    """Exports a simple MAPDL model: timber beam + optional slotted-in steel plate."""

    def __init__(self, element_size_mm: float = 100.0):
        self.element_size_mm = element_size_mm

    # -------------------------------------------------------------------------
    # MATERIAL DEFINITIONS
    # -------------------------------------------------------------------------
    def _material_block_wood(self, mat_id: int, timber: TimberDesign) -> str:
        """Define orthotropic timber material (MAT = mat_id)."""
        e = timber.elastic
        lines = [
            "/PREP7",
            "! --- TIMBER MATERIAL ---",
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
        ]
        return "\n".join(lines)

    def _material_block_steel(self, mat_id: int) -> str:
        """Define isotropic steel material (approximately S355)."""
        return "\n".join([
            "! --- STEEL MATERIAL ---",
            f"mp,ex,{mat_id},210e9",
            f"mp,prxy,{mat_id},0.3",
            "",
        ])

    # -------------------------------------------------------------------------
    # ELEMENT TYPE
    # -------------------------------------------------------------------------
    def _element_block(self, et_id: int = 1) -> str:
        """Define SOLID186."""
        return "\n".join([
            "! --- ELEMENT TYPE ---",
            f"et,{et_id},186",
            "",
        ])

    # -------------------------------------------------------------------------
    # GEOMETRY CREATION
    # -------------------------------------------------------------------------
    def _beam_block(self, geo: Geometry) -> str:
        """Create the main timber beam volume. No material assigned here."""
        L = geo.beam_length
        B = geo.beam_width
        H = geo.beam_height

        return "\n".join([
            "! --- TIMBER BEAM VOLUME (VOLU 1) ---",
            f"block,0,{L}, 0,{B}, 0,{H}",
            "",
        ])

    def _slot_and_plate(self, geo: Geometry) -> str:
        """
        Create a slot and a steel plate volume.
        Only geometry; no materials assigned here.
        """
        L = geo.beam_length
        B = geo.beam_width
        H = geo.beam_height
        sd = geo.slot_depth
        tp = geo.plate_thickness

        slot_z1 = H / 2.0 - tp / 2.0
        slot_z2 = H / 2.0 + tp / 2.0

        lines: list[str] = []

        lines.append("! --- SLOT AND STEEL PLATE ---")
        lines.append(f"! Beam length {L}, slot depth {sd}, plate thickness {tp}")
        lines.append("")

        if sd <= 0:
            lines.append("! Slot depth <= 0 → no slot and no plate created")
            lines.append("")
            return "\n".join(lines)

        # --- Create the slot volume ---
        lines.extend([
            "! Create slot volume",
            f"block,0,{sd}, 0,{B}, {slot_z1},{slot_z2}",
            "*get,vid_slot,volu,0,num,max",
            "",
            "! Subtract slot from timber beam (VOLU 1) and delete slot volume",
            "vsbv,1,vid_slot",
            "vdele,vid_slot",  # delete the temporary slot volume
            "allsel,all",
            "",
        ])


        # --- Create steel plate ---
        lines.extend([
            "! Create steel plate volume (after subtraction)",
            f"block,0,{sd}, 0,{B}, {slot_z1},{slot_z2}",
            "",
        ])

        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # MATERIAL ASSIGNMENT AFTER GEOMETRY
    # -------------------------------------------------------------------------
    def _assign_materials_two_volumes(self, mat_wood: int, mat_steel: int, et_id: int) -> str:
        """Assign MAT/TYP after geometry is complete (beam + plate)."""
        return "\n".join([
            "! --- MATERIAL ASSIGNMENT (BEAM + PLATE) ---",
            "*get,v_beam,volu,0,num,min",
            "*get,v_plate,volu,0,num,max",
            f"type,{et_id}",
            "",
            "! Timber beam",
            "vsel,s,volu,,v_beam",
            f"vatt,{mat_wood},,{et_id}",
            "",
            "! Steel plate",
            "vsel,s,volu,,v_plate",
            f"vatt,{mat_steel},,{et_id}",
            "",
            "allsel,all",
            "",
        ])

    def _assign_material_single_volume(self, mat_wood: int, et_id: int) -> str:
        """If no slot is created, only beam exists."""
        return "\n".join([
            "! --- MATERIAL ASSIGNMENT (ONLY BEAM) ---",
            f"type,{et_id}",
            "vsel,all",
            f"vatt,{mat_wood},,{et_id}",
            "allsel,all",
            "",
        ])

    # -------------------------------------------------------------------------
    # MESH
    # -------------------------------------------------------------------------
    def _mesh_block(self) -> str:
        h = self.element_size_mm
        return "\n".join([
            "! --- MESHING ---",
            "mshape,0,3      ! free 3D meshing, no mapped bricks",
            "mopt,volu,free  ! force free meshing on volumes",
            f"esize,{h}",
            "vmesh,all",
            "finish",
            "",
        ])


    # -------------------------------------------------------------------------
    # EXPORT FUNCTION
    # -------------------------------------------------------------------------
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

        lines: list[str] = []

        # MATERIAL + ELEMENT DEFINITIONS
        lines.append(self._material_block_wood(mat_wood, timber))
        lines.append(self._material_block_steel(mat_steel))
        lines.append(self._element_block(et_id))

        # GEOMETRY
        lines.append(self._beam_block(geo))
        lines.append(self._slot_and_plate(geo))

        # MATERIAL ASSIGNMENT (after all boolean operations)
        if geo.slot_depth > 0:
            lines.append(self._assign_materials_two_volumes(mat_wood, mat_steel, et_id))
        else:
            lines.append(self._assign_material_single_volume(mat_wood, et_id))

        # MESH + SAVE
        lines.append(self._mesh_block())
        

        Path(path).write_text("\n".join(lines))
