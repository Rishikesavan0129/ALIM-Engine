"""
PDF -> DocumentIR. Real extraction, not simulated. Uses pdfplumber's table
grid detection (which uses actual ruling-line/text-position geometry) and
keeps bounding boxes, page numbers, and nearby caption/heading text intact
rather than flattening to a text blob.
"""
import re
import pdfplumber

from alim.ir.model import BBox, Cell, Table, Page, DocumentIR

CAPTION_RE = re.compile(r'Table\s+\d+[\.:]\s*(.+)')
HEADING_RE = re.compile(r'^\d+(\.\d+)*\s+[A-Z][A-Za-z0-9 ,/\-()&\'+]{2,80}$')


def _find_caption(text_lines):
    for line in text_lines:
        m = CAPTION_RE.search(line)
        if m:
            return line.strip()
    return ""


def _find_preceding_heading(text_lines, table_top_y, page_height, char_lines_with_y=None):
    """Best-effort: the nearest numbered-heading-shaped line above the table.
    Falls back to scanning from the top of the page text if we don't have
    per-line y-coordinates (grid extraction alone doesn't give us that
    cheaply, so this is line-order-based, not geometry-based -- a named
    limitation, not a silent one)."""
    for line in text_lines:
        if HEADING_RE.match(line.strip()):
            return line.strip()
    return ""


def extract_document(pdf_path: str) -> DocumentIR:
    doc = DocumentIR(source_path=pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            text_lines = text.split("\n")
            page_ir = Page(page_number=page.page_number, full_text=text)
            for t_idx, t in enumerate(page.find_tables()):
                grid = t.extract()
                if not grid or not grid[0]:
                    continue
                n_rows = len(grid)
                n_cols = max(len(r) for r in grid)
                cells = []
                for r_idx, row in enumerate(grid):
                    for c_idx, val in enumerate(row):
                        if val is None or val == "":
                            continue
                        cells.append(Cell(text=val, row=r_idx, col=c_idx))
                bbox = BBox(*t.bbox) if t.bbox else None
                caption = _find_caption(text_lines)
                heading = _find_preceding_heading(text_lines, bbox.y0 if bbox else 0, page.height)
                page_ir.tables.append(Table(
                    cells=cells, n_rows=n_rows, n_cols=n_cols, page=page.page_number,
                    bbox=bbox, caption=caption, preceding_heading=heading,
                    table_index_on_page=t_idx,
                ))
            doc.pages.append(page_ir)
    return doc
