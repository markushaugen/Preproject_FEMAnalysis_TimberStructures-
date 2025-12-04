# ec5/exporter.py
from pathlib import Path

from .geometry import Geometry
from .connection import FastenerSetup
from .design_values import TimberDesign


class MapdlExporter:
    def __init__(self, element_size_mm: float = 100.0):
        # Global element size used for meshing in MAPDL.
        self.element_size_mm = element_size_mm

    def _material_block(self, mat_id: int, timber: TimberDesign) -> str:
        e = timber.elastic
        lines = [
            "/PREP7",
            f"mp,ex,{mat_id},{e.EX}",
            f"mp,ey,{mat_id},{e.EY}",
            f"mp,ez,{mat_id},{e.EZ}",
            f"mp,prxy,{mat_id},{e.PRXY}",
            f"mp,pryz,{mat_id},{e.PRYZ}",
            f"mp,prxz,{mat_id},{e.PRXZ}",
            f"mp,gxy,{mat_id},{e.GXY}",
            f"mp,gyz,{mat_id},{e.GYZ}",
            f"mp,gxz,{mat_id},{e.GXZ}",
        ]
        return "\n".join(lines)

    def _element_block(self, et_id: int = 1) -> str:
        # SOLID186 is a common 3D structural solid element.
        return f"et,{et_id},186"

    def _geometry_block(self, geo: Geometry, mat_id: int = 1) -> str:
        # Beam block: X = length, Y = width, Z = height (all in mm).
        L = geo.beam_length
        B = geo.beam_width
        H = geo.beam_height
        lines = [
            f"block,0,{L}, 0,{B}, 0,{H}",
            f"vatt,{mat_id},all",  # assign material to all volumes
        ]
        return "\n".join(lines)

    def _mesh_block(self) -> str:
        h = self.element_size_mm
        return "\n".join([
            f"esize,{h}",
            "vmesh,all",
            "finish",
        ])

    def export_mapdl_model(
        self,
        path: str,
        timber: TimberDesign,
        geo: Geometry,
        setup: FastenerSetup | None = None,
        model_name: str = "timber_model",
    ) -> None:
        mat_id = 1
        et_id = 1

        lines: list[str] = []
        lines.append(self._material_block(mat_id, timber))
        lines.append(self._element_block(et_id))
        lines.append(self._geometry_block(geo, mat_id))
        lines.append(self._mesh_block())
        lines.append(f"/save,'{model_name}','db'")

        Path(path).write_text("\n".join(lines))
