# ec5/exporter.py
from pathlib import Path

from .geometry import Geometry
from .connection import FastenerSetup
from .design_values import TimberDesign


class MapdlExporter:
    """Exports a simple MAPDL model: timber beam + slotted-in steel plate."""

    def __init__(self, element_size_mm: float = 100.0):
        self.element_size_mm = element_size_mm

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
        """Define an isotropic steel material (e.g. S355, MAT = mat_id)."""
        lines = [
            "! --- STEEL MATERIAL (MAT=2, S355 approx.) ---",
            f"mp,ex,{mat_id},210e9",
            f"mp,prxy,{mat_id},0.3",
            "",
        ]
        return "\n".join(lines)

    def _element_block(self, et_id: int = 1) -> str:
        """Define solid element type."""
        lines = [
            "! --- ELEMENT TYPE ---",
            f"et,{et_id},186",
            "",
        ]
        return "\n".join(lines)

    def _beam_block(self, geo: Geometry, mat_id: int) -> str:
        """
        Create the main timber beam volume (VOLU 1).
        """
        L = geo.beam_length
        B = geo.beam_width
        H = geo.beam_height

        lines = [
            "! --- TIMBER BEAM VOLUME (VOLU 1) ---",
            f"block,0,{L}, 0,{B}, 0,{H}",

            "!", ";; FIXED MATERIAL ASSIGNMENT FOR TIMBER",
            "*get,vid_beam,volu,0,num,max",     # pick last created volume
            "vsel,s,volu,,vid_beam",
            f"vatt,{mat_id}",
            "allsel,all",
            "",
        ]
        return "\n".join(lines)

    def _slot_and_plate(self, geo: Geometry, mat_wood: int, mat_plate: int) -> str:
        """
        Create a slotted region and insert a steel plate.
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
        lines.append(f"! Beam length L={L}, slot depth sd={sd}, plate t={tp}")
        lines.append("")

        if sd <= 0.0:
            lines.append("! Slot depth <= 0 -> skip slot & plate creation")
            lines.append("")
            return "\n".join(lines)

        # --- Create the slot volume ---
        lines.extend([
            "! Create slot volume",
            f"block,0,{sd}, 0,{B}, {slot_z1},{slot_z2}",

            "!", ";; GET SLOT ID",
            "*get,vid_slot,volu,0,num,max",
            "",
        ])

        # --- Subtract slot from timber beam ---
        lines.extend([
            "! Subtract slot from timber beam",
            "vsbv,1,vid_slot",
            "allsel,all",
            "",
        ])

        # --- Create steel plate (same size as slot) ---
        lines.extend([
            "! Create steel plate volume",
            f"block,0,{sd}, 0,{B}, {slot_z1},{slot_z2}",

            "!", ";; FIXED MATERIAL ASSIGNMENT FOR STEEL",
            "*get,vid_plate,volu,0,num,max",
            "vsel,s,volu,,vid_plate",
            f"vatt,{mat_plate}",
            "allsel,all",
            "",
        ])

        return "\n".join(lines)

    def _mesh_block(self) -> str:
        h = self.element_size_mm
        return "\n".join([
            "! --- MESHING ---",
            f"esize,{h}",
            "vmesh,all",
            "finish",
            "",
        ])

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

        lines.append(self._material_block_wood(mat_wood, timber))
        lines.append(self._material_block_steel(mat_steel))
        lines.append(self._element_block(et_id))

        lines.append(self._beam_block(geo, mat_wood))
        lines.append(self._slot_and_plate(geo, mat_wood, mat_steel))

        lines.append(self._mesh_block())
        lines.append(f"/save,'{model_name}','db'")

        Path(path).write_text("\n".join(lines))

