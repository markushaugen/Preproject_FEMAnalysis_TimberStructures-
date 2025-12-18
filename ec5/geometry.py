# ec5/geometry.py
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Geometry:
    beam_length: float        
    beam_height: float        
    beam_width: float         
    plate_thickness: float    
    slot_depth: float         
    num_dowels: int
    dowel_diameter: float     
    dowel_spacing: float      
    edge_distance: float      
    row_offset: float = 0.0   

    def validate(self) -> None:
        # Basic sanity checks
        assert self.beam_length > 0 and self.beam_height > 0 and self.beam_width > 0, "Beam dims must be > 0"
        assert 0 <= self.slot_depth < self.beam_height, "Slot depth must be less than beam height"
        assert self.num_dowels >= 1, "At least one dowel is required"
        assert self.dowel_diameter > 0, "Dowel diameter must be > 0"
        assert self.plate_thickness > 0, "Plate thickness must be > 0"
        assert self.dowel_spacing > 0, "Dowel spacing must be > 0"
        assert self.edge_distance > 0, "Edge distance must be > 0"

        # Dowel row within z bounds
        z_row = self.beam_height / 2.0 + self.row_offset
        assert 0.0 < z_row < self.beam_height, "Dowel row must lie inside the beam height"

        # Fit along beam length
        min_length_needed = 2 * self.edge_distance + max(0, self.num_dowels - 1) * self.dowel_spacing
        assert self.beam_length >= min_length_needed, (
            f"Beam is too short for the selected dowel pattern: ≥ {min_length_needed:.1f} mm, "
            f"have {self.beam_length:.1f} mm"
        )

        d = self.dowel_diameter

        # Along-grain end distance a3,t ≥ 7d
        min_a3 = 7 * d
        assert self.edge_distance >= min_a3, (
            f"End distance a3 = {self.edge_distance:.1f} mm < 7d = {min_a3:.1f} mm"
        )

        # Along-grain spacing s ≥ 5d
        min_s = 5 * d
        if self.num_dowels > 1:
            assert self.dowel_spacing >= min_s, (
                f"Center distance s = {self.dowel_spacing:.1f} mm < 5d = {min_s:.1f} mm"
            )

        # Across-grain edge distance a2 ≥ 4d 
        min_a2 = 4 * d
        a2_top = self.beam_height - z_row
        a2_bot = z_row
        a2_min = min(a2_top, a2_bot)
        assert a2_min >= min_a2, (
            f"Across-grain edge distance a2 = {a2_min:.1f} mm < 4d = {min_a2:.1f} mm. "
            "Increase beam height or adjust row position."
        )

        # Slot margin in height 
        remain_top = a2_top - self.slot_depth
        remain_bot = a2_bot - self.slot_depth
        remain_min = min(remain_top, remain_bot)
        assert remain_min >= min_a2, (
            f"Remaining timber from slot to edge = {remain_min:.1f} mm < 4d = {min_a2:.1f} mm. "
            "Reduce slot depth or increase beam height."
        )

    def dowel_positions(self) -> List[Tuple[float, float]]:
        """
        Returns (x, z) coordinates in millimetres for a single dowel row.
        x: along the beam length from the left end,
        z: measured upward from the bottom edge.
        """
        x0 = self.edge_distance
        z = self.beam_height / 2.0 + self.row_offset
        return [(x0 + i * self.dowel_spacing, z) for i in range(self.num_dowels)]
