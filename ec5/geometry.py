# ec5/geometry.py
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Geometry:
    beam_length: float = 1000
    beam_height: float =  200 # Y-direction in MAPDL
    beam_width: float = 100   # Z-direction in MAPDL (thickness)
    plate_thickness: float = 10.0

    slot_x1: float = 600
    slot_x2: float = 1000
    slot_y1: float = 30
    slot_y2: float = 170
    clearance_y: float = 2.0
    plate_slot_clearance_y: float = 1.0  
    dowels_from_right: bool = True
    num_dowels: int = 4
    dowel_diameter: float = 16
    dowel_spacing: float = 100
    edge_distance: float = 100
    row_offset: float = 0.0

    def validate(self) -> None:
        # Basic sanity checks
        assert self.beam_length > 0 and self.beam_height > 0 and self.beam_width > 0, "Beam dims must be > 0"
        assert 0 <= self.slot_x1 < self.slot_x2 <= self.beam_length, "Slot x-range must satisfy 0 <= x1 < x2 <= L"
        assert 0 <= self.slot_y1 < self.slot_y2 <= self.beam_height, "Slot y-range must satisfy 0 <= y1 < y2 <= H"
        assert 0 <= self.clearance_y < (self.slot_y2 - self.slot_y1), "clearance_y must be smaller than slot height in Y"
        assert self.num_dowels >= 1, "At least one dowel is required"
        assert self.dowel_diameter > 0, "Dowel diameter must be > 0"
        assert self.plate_thickness <= self.beam_width, "Plate thickness must be <= beam width (Z-direction)"
        assert self.dowel_spacing > 0, "Dowel spacing must be > 0"
        assert self.edge_distance > 0, "Edge distance must be > 0"

        # Dowel row within Y bounds
        y_row = self.beam_height / 2.0 + self.row_offset
        assert 0.0 < y_row < self.beam_height, "Dowel row must lie inside the beam height (Y)"

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

        # Across-grain edge distance check in Y-direction (simple symmetric assumption)
        min_a2 = 4 * d
        a2_top = self.beam_height - y_row
        a2_bot = y_row
        a2_min = min(a2_top, a2_bot)
        assert a2_min >= min_a2, (
            f"Across-grain edge distance a2 = {a2_min:.1f} mm < 4d = {min_a2:.1f} mm. "
            "Increase beam height or adjust row position."
        )

    def dowel_positions(self) -> List[Tuple[float, float]]:
        y = self.beam_height / 2.0 + self.row_offset

        if self.dowels_from_right:
            x_last = self.beam_length - self.edge_distance
            x0 = x_last - (self.num_dowels - 1) * self.dowel_spacing
        else:
            x0 = self.edge_distance

        return [(x0 + i * self.dowel_spacing, y) for i in range(self.num_dowels)]




