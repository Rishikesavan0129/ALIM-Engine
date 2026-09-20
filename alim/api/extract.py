"""
Top-level API. One function: extract(pdf_path, query, vlm_provider=None).

Returns a plain dict matching the output shapes specified for the engine:
VERIFIED-style success, AMBIGUOUS, AMBIGUOUS_MISSING_CONDITION, NOT_FOUND,
SCHEMA_UNKNOWN, VLM_REQUIRED. No field is ever fabricated -- an absent
condition/unit stays absent rather than being guessed.

Orchestration principle (the actual point of this module): the structural
pass runs first and reduces the search space -- only pages where a
table-shaped grid was found but its schema could not be confidently
classified are ever passed to a VLM provider. A document is never blindly
sent page-by-page to a VLM; that would defeat the "minimum VLM computation
necessary" requirement. If no vlm_provider is given, behavior is identical
to structural-only extraction (existing tests rely on this).
"""
import time

from alim.ingestion.pdf_extract import extract_document
from alim.candidates.build import build_candidates_from_table
from alim.schema.classify import classify_table_shape
from alim.decision.core import extract_parameter, STATUS_FOUND


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
            include_unresolved: bool = False, include_all_evidence: bool = False) -> dict:
    """include_unresolved: on a real, complex datasheet the grid detector
    flags many non-data regions (figures, pin diagrams, revision-history
    tables) as "unsupported tables" -- on a 78-page document this can be
    100+ entries. Section 23's requirement is that the normal successful
    case stays simple, so this noise is OFF by default and only surfaced
    when the caller explicitly asks (debugging) or when the result is
    itself a refusal, where it's the actual answer, not noise."""
    doc = extract_document(pdf_path)

    all_candidates = []
    unsupported_tables = []
    unsupported_pages = set()
    for page in doc.pages:
        for table in page.tables:
            grid = table.grid()
            if not grid or not grid[0]:
                continue
            shape = classify_table_shape(grid[0])
            if shape not in ("spec_table", "single_value_table"):
                unsupported_tables.append({"page": table.page, "schema": shape,
                                             "header": " | ".join(c for c in grid[0] if c)})
                unsupported_pages.add(table.page)
                continue
            all_candidates.extend(build_candidates_from_table(table))

    # Two-phase: decide on structural evidence alone first. Only escalate to
    # the VLM if the structural pass didn't already produce a confident
    # answer -- otherwise a page that resolves fine can still trigger a
    # wasted VLM call just because it ALSO happens to contain an unrelated
    # junk "table" (e.g. a figure the grid detector misdetects). Found via
    # test_vlm_only_called_for_pages_with_unresolved_tables_not_every_page:
    # the first version called the VLM on a page that had already produced
    # the correct answer, purely because that same page had an unrelated
    # unsupported table elsewhere on it.
    structural_decision = extract_parameter(all_candidates, query)

    vlm_calls = []
    decision = structural_decision
    if structural_decision.status != STATUS_FOUND and vlm_provider is not None and unsupported_pages:
        vlm_candidates = []
        for page_number in sorted(unsupported_pages):
            t0 = time.time()
            try:
                page_candidates = vlm_provider.perceive(pdf_path, page_number, query)
            except Exception as exc:
                vlm_calls.append({"page": page_number, "latency_s": round(time.time() - t0, 3),
                                    "error": str(exc), "n_candidates": 0})
                continue
            vlm_calls.append({"page": page_number, "latency_s": round(time.time() - t0, 3),
                                "n_candidates": len(page_candidates)})
            vlm_candidates.extend(page_candidates)
        if vlm_candidates:
            decision = extract_parameter(all_candidates + vlm_candidates, query)

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
                       "reason": "No table with a recognized schema was found" +
                                 ("" if vlm_provider is None else ", and the configured VLM provider "
                                  "did not return usable evidence either") + "; refusing rather than guessing.",
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

    if vlm_calls:
        result["vlm_calls"] = vlm_calls  # always visible, not gated -- this is cost/latency evidence, not noise

    if include_all_evidence:
        # Everything the engine actually saw and considered, whether or not
        # it matched the query -- so a failed/partial result is never a dead
        # end. Every candidate that reached extract_parameter ends up in
        # either decision.accepted or decision.rejected; together they are
        # the complete set considered for this query.
        evidence = [dict(_candidate_to_dict(c), outcome="accepted") for c in decision.accepted]
        for c, reason in decision.rejected:
            entry = _candidate_to_dict(c)
            entry["outcome"] = "rejected"
            entry["reason"] = reason
            evidence.append(entry)
        result["all_evidence"] = evidence

    if trace:
        result["_trace"] = decision.trace.steps
    return result
