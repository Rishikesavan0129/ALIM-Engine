"""
Intermediate representation (IR) for a parsed datasheet page.

Honest scope note: this preserves what pdfplumber's grid/word extraction
actually gives us -- bounding boxes, page numbers, cell grid position, and
nearby caption/heading text. It does NOT currently preserve font metadata,
true reading-order across multi-column layouts, or merged-cell spans as a
first-class structure (a merged header still arrives as a grid row with
empty cells, same as before; see schema.classify for how that's handled).
Those are named gaps, not silent ones -- see LIMITATIONS.md.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Cell:
    text: str                  # raw text, NOT normalized -- normalization is schema/candidates' job
    row: int
    col: int
    bbox: Optional[BBox] = None


@dataclass
class Table:
    cells: List[Cell]
    n_rows: int
    n_cols: int
    page: int
    bbox: Optional[BBox] = None
    caption: str = ""           # e.g. "Table 2. Absolute maximum ratings" -- found near the table, not from it
    preceding_heading: str = "" # e.g. "3 Absolute maximum ratings" -- the heading above, if any
    table_index_on_page: int = 0

    def grid(self) -> List[List[str]]:
        """Reconstruct a 2D grid of raw cell text, empty string for holes."""
        grid = [["" for _ in range(self.n_cols)] for _ in range(self.n_rows)]
        for c in self.cells:
            if 0 <= c.row < self.n_rows and 0 <= c.col < self.n_cols:
                grid[c.row][c.col] = c.text
        return grid


@dataclass
class Page:
    page_number: int
    full_text: str
    tables: List[Table] = field(default_factory=list)


@dataclass
class DocumentIR:
    source_path: str
    pages: List[Page] = field(default_factory=list)
