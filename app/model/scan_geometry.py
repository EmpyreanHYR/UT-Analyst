"""Scan position and C-scan geometry helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class ScanPosition:
    """One raster scan coordinate."""

    index: int
    x_mm: float
    y_mm: float


class ScanGrid:
    """Map linear frame indexes onto a raster scan grid."""

    def __init__(
        self,
        rows: int,
        columns: int,
        row_spacing_mm: float,
        column_spacing_mm: float,
    ) -> None:
        if rows < 1 or columns < 1:
            raise ValueError("扫描网格行列数必须大于0")
        self.rows = int(rows)
        self.columns = int(columns)
        self.row_spacing_mm = float(row_spacing_mm)
        self.column_spacing_mm = float(column_spacing_mm)

    def position_for_index(self, index: int) -> tuple[float, float]:
        """Return the x/y coordinate for a linear frame index."""
        normalized = int(index) % (self.rows * self.columns)
        row = normalized // self.columns
        column = normalized % self.columns
        return column * self.column_spacing_mm, row * self.row_spacing_mm

    def build_c_scan(
        self,
        values: Iterable[tuple[int, float]],
        initial_value: float = 0.0,
    ) -> np.ndarray:
        """Build a C-scan matrix, retaining the maximum amplitude per cell."""
        matrix = np.full((self.rows, self.columns), float(initial_value), dtype=np.float32)
        for index, value in values:
            normalized = int(index) % (self.rows * self.columns)
            row = normalized // self.columns
            column = normalized % self.columns
            matrix[row, column] = max(matrix[row, column], float(value))
        return matrix
