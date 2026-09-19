"""
Evidence-related code currently lives alongside what it documents rather
than in a separate module: per-candidate evidence (page, table/row index,
section, confidence, schema) is `Candidate.evidence_dict()` in
`alim.candidates.build`, and the per-extraction explainable trace is
`alim.decision.core.Trace`. This package is reserved for a dedicated
evidence-persistence layer (e.g. writing evidence records to a database for
audit) if/when that becomes a real requirement -- not implemented yet.
"""
