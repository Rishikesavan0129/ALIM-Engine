"""
Top-level API. One function: extract(pdf_path, query, vlm_provider=None).

Returns a plain dict matching the output shapes specified for the engine:
VERIFIED-style success, AMBIGUOUS, AMBIGUOUS_MISSING_CONDITION, NOT_FOUND,
SCHEMA_UNKNOWN, VLM_REQUIRED. No field is ever fabricated -- an absent
condition/unit stays absent rather than being guessed.
"""
from alim.ingestion.pdf_extract import extract_document
from alim.candidates.build import build_candidates_from_table
from alim.schema.classify import classify_table_shape
from alim.decision.core import extract_parameter, STATUS_FOUND
from alim.vlm.interface import NoVLMConfigured


def _candidate_to_dict(c):
    value = c.max_val if (c.min_val and c.max_val and c.min_val != c.max_val) else (
        c.typ_val or c.max_val or c.min_val)
    if c.min_val and c.max_val and c.min_val != c.max_val:
        value = f"{c.min_val}\u2013{c.max_val}"
    return {
        "parameter": c.detected_parameter, "symbol": c.symbol, "value": value,
        "unit": c.unit, "condition": c.condition or None, "page": c.page,
        "evidence": c.evidence_dict(),
    }


def extract(pdf_path: str, query: str, vlm_provider=None, trace: bool = False,
            include_unresolved: bool = False) -> dict:
    """include_unresolved: on a real, complex datasheet the grid detector
    flags many non-data regions (figures, pin diagrams, revision-history
    tables) as "unsupported tables" -- on a 78-page document this can be
    100+ entries. Section 23's requirement is that the normal successful
    case stays simple, so this noise is OFF by default and only surfaced
    when the caller explicitly asks (debugging) or when the result is
    itself a refusal, where it's the actual answer, not noise."""
    if vlm_provider is None:
        vlm_provider = NoVLMConfigured()

    doc = extract_document(pdf_path)

    all_candidates = []
    unsupported_tables = []
    for page in doc.pages:
        for table in page.tables:
            grid = table.grid()
            if not grid or not grid[0]:
                continue
            shape = classify_table_shape(grid[0])
            if shape not in ("spec_table", "single_value_table"):
                unsupported_tables.append({"page": table.page, "schema": shape,
                                             "header": " | ".join(c for c in grid[0] if c)})
                continue
            all_candidates.extend(build_candidates_from_table(table))

    decision = extract_parameter(all_candidates, query)

    if decision.status == STATUS_FOUND:
        result = {
            "parameter": decision.accepted[0].detected_parameter,
            "status": "VERIFIED" if all(c.section_confidence == "VERIFIED" for c in decision.accepted) else "FOUND",
            "results": [_candidate_to_dict(c) for c in decision.accepted],
        }
        if decision.caveats:
            result["caveats"] = decision.caveats
    elif decision.status == "NOT_FOUND":
        if all_candidates or not unsupported_tables:
            result = {"parameter": query, "status": "NOT_FOUND",
                       "reason": "No matching candidate found in any successfully-parsed table."}
        else:
            result = {"parameter": query, "status": "SCHEMA_UNKNOWN",
                       "reason": "No table with a recognized schema was found; refusing rather than guessing.",
                       "unsupported_tables": unsupported_tables[:20]}
    else:  # AMBIGUOUS / AMBIGUOUS_MISSING_CONDITION
        result = {
            "parameter": query, "status": decision.status, "reason": decision.notes,
            "candidates": [_candidate_to_dict(c) for c in decision.accepted],
        }

    if unsupported_tables and decision.status == STATUS_FOUND and include_unresolved:
        result["unresolved_tables"] = unsupported_tables[:20]
    elif unsupported_tables and decision.status == STATUS_FOUND:
        result["unresolved_table_count"] = len(unsupported_tables)  # visible but not noisy

    if trace:
        result["_trace"] = decision.trace.steps
    return result
