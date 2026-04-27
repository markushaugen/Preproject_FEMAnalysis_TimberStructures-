# ec5/geometry.py
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Geometry:
    beam_length: float = 1000
    beam_height: float =  200 # Y-direction in MAPDL
    beam_width: float = 100   # Z-direction in MAPDL (thickness)
    plate_thickness: float = 10.0

    slot_y1: float = 30
    slot_y2: float = 170
    clearance_y: float = 0.0
    plate_slot_clearance_y: float = 0.5
    beam_hole_clearance: float = 0.0
    plate_hole_clearance: float = 0.0
    dowels_from_right: bool = True
    n_rows: int = 1       # rows perpendicular to grain (Y-direction)
    n_cols: int = 4       # dowels along grain (X-direction) per row
    dowel_diameter: float = 20
    dowel_spacing: float = 100  # along-grain spacing between dowels (X)
    edge_distance: float = 100
    row_spacing: float = 60.0  # perpendicular spacing between adjacent rows (Y)
    row_offset: float = 0.0
    make_beam_holes: bool = True
    make_plate_slots: bool = True
    n_plates: int = 1

    @property
    def num_dowels(self) -> int:
        return self.n_rows * self.n_cols

    def _row_y_positions(self) -> List[float]:
        """Y-coordinates of each row, centered on beam mid-height + row_offset."""
        center = self.beam_height / 2.0 + self.row_offset
        if self.n_rows == 1:
            return [center]
        total_span = (self.n_rows - 1) * self.row_spacing
        y_start = center - total_span / 2.0
        return [y_start + i * self.row_spacing for i in range(self.n_rows)]

    def plate_z_centers(self) -> List[float]:
        """Z-center of each plate per EC5 5d rule, symmetric about B/2."""
        d = self.dowel_diameter
        t = self.plate_thickness
        B = self.beam_width
        if self.n_plates == 1:
            return [B / 2.0]
        elif self.n_plates == 2:
            return [5 * d + t / 2.0, B - 5 * d - t / 2.0]
        else:
            zc = B / 2.0
            return [zc - (5 * d + t), zc, zc + (5 * d + t)]

    def min_beam_width_for_n_plates(self) -> float:
        """Minimum B required by EC5 5d edge + inter-plate gap rules."""
        d = self.dowel_diameter
        t = self.plate_thickness
        if self.n_plates == 1:
            return 10 * d + t
        elif self.n_plates == 2:
            return 15 * d + 2 * t
        else:
            return 20 * d + 3 * t

    def validate(self) -> None:
        assert self.beam_length > 0 and self.beam_height > 0 and self.beam_width > 0, "Beam dims must be > 0"
        assert 0 <= self.slot_y1 < self.slot_y2 <= self.beam_height, "Slot y-range must satisfy 0 <= y1 < y2 <= H"
        assert 0 <= self.clearance_y < (self.slot_y2 - self.slot_y1), "clearance_y must be smaller than slot height in Y"
        assert self.n_rows >= 1, "At least one row is required"
        assert self.n_cols >= 1, "At least one column is required"
        assert self.dowel_diameter > 0, "Dowel diameter must be > 0"
        assert self.plate_thickness <= self.beam_width, "Plate thickness must be <= beam width (Z-direction)"
        assert self.dowel_spacing > 0, "Dowel spacing must be > 0"
        assert self.edge_distance > 0, "Edge distance must be > 0"
        assert self.beam_hole_clearance >= 0.0, "beam_hole_clearance must be >= 0"
        assert self.plate_hole_clearance >= 0.0, "plate_hole_clearance must be >= 0"
        assert self.plate_slot_clearance_y >= 0.0, "plate_slot_clearance_y must be >= 0"
        assert self.clearance_y >= 0.0, "clearance_y must be >= 0"
        assert self.slot_y2 - self.slot_y1 > self.clearance_y, "Plate slot height must be larger than clearance_y"
        assert self.n_plates in (1, 2, 3), "n_plates must be 1, 2, or 3"

        if self.plate_thickness > 0 and self.n_plates >= 1:
            min_B = self.min_beam_width_for_n_plates()
            if self.beam_width < min_B:
                print(
                    f"[WARNING] B = {self.beam_width:.1f} mm is too narrow for {self.n_plates} plate(s) "
                    f"with EC5 5d rule. Minimum required B = {min_B:.1f} mm "
                    f"(5d={5*self.dowel_diameter:.0f} mm edge distances + "
                    f"plate thicknesses + 5d inter-plate gaps)."
                )

        d = self.dowel_diameter
        y_positions = self._row_y_positions()

        if self.n_rows > 1:
            assert self.row_spacing > 0, "row_spacing must be > 0"
            # Perpendicular spacing between adjacent rows a2 ≥ 3d (EC5 Table 8.2)
            min_a2_rows = 3 * d
            assert self.row_spacing >= min_a2_rows, (
                f"Row spacing = {self.row_spacing:.1f} mm < 3d = {min_a2_rows:.1f} mm"
            )

        # All rows must lie within beam height
        for y in y_positions:
            assert 0.0 < y < self.beam_height, f"Dowel row at y={y:.1f} mm must lie inside beam height (Y)"

        # Edge distance from outermost rows to beam edge ≥ 4d
        min_a2_edge = 4 * d
        a2_min = min(min(y_positions), self.beam_height - max(y_positions))
        assert a2_min >= min_a2_edge, (
            f"Across-grain edge distance a2 = {a2_min:.1f} mm < 4d = {min_a2_edge:.1f} mm. "
            "Increase beam height, reduce row_spacing, or adjust row_offset."
        )

        # Fit along beam length
        min_length_needed = 2 * self.edge_distance + max(0, self.n_cols - 1) * self.dowel_spacing
        assert self.beam_length >= min_length_needed, (
            f"Beam is too short for the selected dowel pattern: ≥ {min_length_needed:.1f} mm, "
            f"have {self.beam_length:.1f} mm"
        )

        # Along-grain end distance a3,t ≥ 7d
        min_a3 = 7 * d
        assert self.edge_distance >= min_a3, (
            f"End distance a3 = {self.edge_distance:.1f} mm < 7d = {min_a3:.1f} mm"
        )

        # Along-grain spacing s ≥ 5d
        min_s = 5 * d
        if self.n_cols > 1:
            assert self.dowel_spacing >= min_s, (
                f"Center distance s = {self.dowel_spacing:.1f} mm < 5d = {min_s:.1f} mm"
            )

    def plate_extents(self) -> Tuple[float, float]:
        """Plate x-extents: from (leftmost dowel - edge_distance) to beam end."""
        xs = [x for x, _ in self.dowel_positions()]
        x1 = min(xs) - self.edge_distance
        x2 = self.beam_length
        return (x1, x2)

    def dowel_positions(self) -> List[Tuple[float, float]]:
        y_positions = self._row_y_positions()

        if self.dowels_from_right:
            x_last = self.beam_length - self.edge_distance
            x0 = x_last - (self.n_cols - 1) * self.dowel_spacing
        else:
            x0 = self.edge_distance

        x_positions = [x0 + i * self.dowel_spacing for i in range(self.n_cols)]
        return [(x, y) for y in y_positions for x in x_positions]




