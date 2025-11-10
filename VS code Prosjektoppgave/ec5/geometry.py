# ec5/geometry.py
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Geometry:
    beam_length: float        # [mm]
    beam_height: float        # [mm]
    beam_width: float         # [mm]  # limtretykkelse
    plate_thickness: float    # [mm]
    slot_depth: float         # [mm]  # innfelling
    num_dowels: int
    dowel_diameter: float     # [mm]
    dowel_spacing: float      # [mm]  # senter–senter i lengderetning
    edge_distance: float      # [mm]  # endeavstand
    row_offset: float = 0.0   # [mm]  # for ev. rad nr. 2 senere

    def validate(self) -> None:
        assert self.beam_length > 0 and self.beam_height > 0 and self.beam_width > 0
        assert 0 <= self.slot_depth < self.beam_height, "Slot dypere enn bjelkehøyde"
        assert self.num_dowels >= 1, "Minst én dybel"
        min_length_needed = 2*self.edge_distance + max(0, self.num_dowels-1)*self.dowel_spacing
        assert self.beam_length >= min_length_needed, "Bjelken er for kort til valgt mønster"

    def dowel_positions(self) -> List[Tuple[float, float]]:
        """Returnerer (x,z) i mm for én rad midt i bjelkens bredde.
        x: langs bjelken fra venstre ende, z: fra bunnkant opp."""
        x0 = self.edge_distance
        z = self.beam_height / 2.0
        return [(x0 + i*self.dowel_spacing, z) for i in range(self.num_dowels)]
