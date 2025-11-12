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
        """
        Basic geometry checks + EC5-like minimum spacing/edge distances for a single dowel/bolt row.
        Units here are mm (consistent with your CLI).
        """
        # --- Basic sanity ---
        assert self.beam_length > 0 and self.beam_height > 0 and self.beam_width > 0, "Beam dims must be > 0"
        assert 0 <= self.slot_depth < self.beam_height, "Slot depth must be less than beam height"
        assert self.num_dowels >= 1, "At least one dowel is required"
        assert self.dowel_diameter > 0, "Dowel diameter must be > 0"
        assert self.plate_thickness > 0, "Plate thickness > 0"
        assert self.dowel_spacing > 0, "Dowel spacing > 0"
        assert self.edge_distance > 0, "Edge distance > 0"

        # --- Fit in length (row along the beam axis) ---
        min_length_needed = 2 * self.edge_distance + max(0, self.num_dowels - 1) * self.dowel_spacing
        assert self.beam_length >= min_length_needed, (
            f"BBeam is too short for the selected dowel pattern: ≥ {min_length_needed:.1f} mm, "
            f"have {self.beam_length:.1f} mm"
        )

        # --- EC5-ish minimums (conservative, single row) ---
        d = self.dowel_diameter

        # Along-grain end distance (a3) — conservative 7d
        min_a3 = 7 * d
        assert self.edge_distance >= min_a3, f"End distance a3 = {self.edge_distance:.1f} mm < 7d = {min_a3:.1f} mm"

        # Along-grain spacing (s) — conservative 5d
        min_s = 5 * d
        if self.num_dowels > 1:
            assert self.dowel_spacing >= min_s, f"Center dictance s = {self.dowel_spacing:.1f} mm < 5d = {min_s:.1f} mm"

        # Across-grain edge distance (a2) — conservative 4d from row center to nearest free edge
        # Your dowel_positions() places the row at mid-height -> half_clear is distance to top/bottom.
        min_a2 = 4 * d
        half_clear = 0.5 * self.beam_height
        assert half_clear >= min_a2, (
            f"Across-grain edge distance a2 = {half_clear:.1f} mm < 4d = {min_a2:.1f} mm. "
            "Increase beam height or adjust row position."
        )

        # Slot margin in height (avoid slot biting too much into the a2 margin):
        # Require remaining timber from slot to nearest edge ≥ 4d
        remain_top = 0.5 * self.beam_height - self.slot_depth
        remain_bot = 0.5 * self.beam_height - self.slot_depth
        assert min(remain_top, remain_bot) >= min_a2, (
            f"Remaining timber from slot to edge = {min(remain_top, remain_bot):.1f} mm < 4d = {min_a2:.1f} mm. "
            "Reduce slot depth or increase beam height."
        )


    def dowel_positions(self) -> List[Tuple[float, float]]:
        """Returns (x, z) coordinates in millimetres for a single dowel row
        positioned at mid-height of the beam.
        x: along the beam length from the left end,
        z: measured upward from the bottom edge."""
        x0 = self.edge_distance
        z = self.beam_height / 2.0
        return [(x0 + i*self.dowel_spacing, z) for i in range(self.num_dowels)]
