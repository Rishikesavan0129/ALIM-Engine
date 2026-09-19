"""
IR Table -> list[Candidate]. This is the "candidate generation" layer: it
does not decide anything, it only reconstructs row-level structure and
schema-appropriate fields. All rejection/acceptance logic lives in
decision/core.py.
"""
import re
from dataclasses import dataclass, field as dc_field
from typing import List

from alim.schema.classify import classify_table_shape, classify_section, FIELD_ALIASES, normalize_header_cell

SUBSCRIPT_JOIN_RE = re.compile(r'^(.*\S) (.{1,10})$')


@dataclass
class Candidate:
    detected_parameter: str
    symbol: str = ""
    condition: str = ""
    min_val: str = ""
    typ_val: str = ""
    max_val: str = ""
    unit: str = ""
    section: str = ""
    section_confidence: str = "NONE"
    table_schema: str = ""
    page: int = 0
    table_index_on_page: int = 0
    row_index: int = -1
    footnote_text: str = ""
    source_region: str = ""

    def evidence_dict(self):
        """Section 13's requirement: traceable evidence for every candidate."""
        return {
            "page": self.page, "table_index_on_page": self.table_index_on_page,
            "row_index": self.row_index, "section": self.section,
            "section_confidence": self.section_confidence, "table_schema": self.table_schema,
        }


def _build_field_map(header_row):
    field_map = {}
    for idx, cell in enumerate(header_row):
        norm = normalize_header_cell(cell).lower()
        if norm in FIELD_ALIASES:
            field_map[FIELD_ALIASES[norm]] = idx

    # General fallback, not a one-off hack: in essentially every real spec
    # table (regardless of manufacturer or exact header wording), the
    # LEFTMOST column is the parameter/label column even when its header
    # text doesn't literally say "Parameter" -- e.g. a real, published
    # Nordic nRF24L01+ table whose column 0 header reads "Operating
    # conditions" while every row beneath it is plainly a parameter name
    # (VDD, VSS, Input voltage, ...). Without this fallback, a table can
    # pass schema classification (it has real Min/Max columns) and still
    # silently produce zero candidates, because no column ever gets
    # identified as holding the parameter name -- exactly Failure 5
    # (schema misdetection causing silent data loss) recurring one level
    # deeper than table-shape classification. Only applies when some
    # numeric column (min/typ/max/value) WAS found, i.e. this is
    # confidently a spec table, just with an unhelpful header label.
    has_numeric_col = any(k in field_map for k in ("min", "typ", "max", "value"))
    if "parameter" not in field_map and "parameter_and_condition" not in field_map and has_numeric_col:
        if 0 not in field_map.values():
            field_map["parameter"] = 0
    return field_map


def _split_subscript_symbol(text):
    """Symbol-column-specific: a PDF subscript (V_DD) commonly extracts as
    two lines, 'V\\nDD'. This is a font/rendering artifact, not two data
    points, so it is always safe to join -- unlike condition/value cells,
    where multiple lines are usually genuinely distinct sub-conditions
    (handled separately by _zip_multiline_row below)."""
    if not text or "\n" not in text:
        return text or ""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) == 2 and len(lines[1]) <= 10 and " " not in lines[1]:
        return lines[0].strip() + lines[1].strip()
    return " / ".join(l.strip() for l in lines)


def _zip_multiline_row(row, field_map):
    """A single grid row can visually stack multiple sub-conditions in one
    cell via aligned newlines across sibling cells -- e.g. condition cell
    'Local Power\\nParasite Power' paired with a min-value cell '2.2\\n3.0'
    and a unit cell 'V\\nV'. Confirmed on two independent real datasheets
    (DS18B20, LM35) -- a general phenomenon, not a one-off. When 2+ of the
    condition/min/typ/max/unit cells share the same >1 line count, split
    into that many rows by zipping corresponding lines. If cells disagree
    on line count, do NOT guess an alignment -- return the row unsplit and
    let value_quality/decision flag whatever looks malformed."""
    keys = ["condition", "min", "typ", "max", "unit"]
    idxs = {k: field_map.get(k) for k in keys}
    line_lists = {}
    for k, idx in idxs.items():
        if idx is None or idx >= len(row) or not row[idx]:
            continue
        lines = row[idx].split("\n")
        if len(lines) > 1:
            line_lists[k] = lines
    if len(line_lists) < 2:
        return [row]  # nothing to zip; leave as-is
    counts = {len(v) for v in line_lists.values()}
    if len(counts) != 1:
        return [row]  # inconsistent line counts -- can't safely align, abstain from splitting
    n = counts.pop()
    split_rows = []
    for i in range(n):
        new_row = list(row)
        for k, idx in idxs.items():
            if k in line_lists:
                new_row[idx] = line_lists[k][i].strip()
        split_rows.append(new_row)
    return split_rows


def build_candidates_from_table(table) -> List[Candidate]:
    grid = table.grid()
    if not grid or not grid[0]:
        return []
    shape = classify_table_shape(grid[0])
    header_text = " | ".join(c for c in grid[0] if c)
    section, confidence = classify_section(table.caption, table.preceding_heading, header_text)

    if shape not in ("spec_table", "single_value_table"):
        return []  # explicit refusal -- callers must check table shape separately to report SCHEMA_UNKNOWN

    field_map = _build_field_map(grid[0])
    symbol_idx = field_map.get("symbol")
    candidates = []
    last_param, last_symbol = "", ""
    for r_idx, raw_row in enumerate(grid[1:], start=1):
        if symbol_idx is not None and symbol_idx < len(raw_row) and raw_row[symbol_idx]:
            raw_row = list(raw_row)
            raw_row[symbol_idx] = _split_subscript_symbol(raw_row[symbol_idx])
        for row in _zip_multiline_row(raw_row, field_map):
            def get(key):
                idx = field_map.get(key)
                return row[idx] if idx is not None and idx < len(row) else ""

            param = get("parameter") or get("parameter_and_condition")
            symbol = get("symbol")
            condition = get("condition") or get("parameter_and_condition")
            if not param and not symbol:
                param, symbol = last_param, last_symbol   # forward-fill continuation row
            else:
                last_param, last_symbol = param, symbol
            if not param and not symbol:
                continue

            typ_val = get("typ") or get("value")   # a single-value-table's "Value" column becomes typ_val
            candidates.append(Candidate(
                detected_parameter=param, symbol=symbol, condition=condition,
                min_val=get("min"), typ_val=typ_val, max_val=get("max"), unit=get("unit"),
                section=section or "", section_confidence=(confidence.value if section else "NONE"),
                table_schema=shape, page=table.page, table_index_on_page=table.table_index_on_page,
                row_index=r_idx, source_region=f"p{table.page}t{table.table_index_on_page}r{r_idx}",
            ))
    return candidates
