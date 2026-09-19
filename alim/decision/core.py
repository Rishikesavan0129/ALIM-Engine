"""
The deterministic decision layer. This is the piece the architecture says
must not be redesigned just because upstream representation is imperfect --
only changed when a reproducible test demonstrates a genuine decision-layer
defect. Two such defects were found and fixed during development (see
tests/test_decision_scenarios.py and CHANGELOG in README): (1) section
classification trusting a table's own header text with no confidence
distinction, and (2) no explicit state for "same table, same parameter,
conflicting values, no distinguishing condition" -- previously silently
folded into a generic "preserve both" outcome with no flag.
"""
import re
from dataclasses import dataclass, field
from typing import List

from alim.candidates.build import Candidate
from alim.schema.classify import Confidence

RESTRICTED_QUERY_MARKERS = ["absolute maximum", "maximum rating", "storage", "esd"]
NUM_RE = re.compile(r'^[-+\u00b1]?\d*\.?\d*[\u00bd\u2153\u2154\u00bc\u00be]?$')
FORMULA_RE = re.compile(r'^[A-Za-z]+\s*[-+]\s*\d+(\.\d+)?$')
SYMBOL_CONCEPT_TERMS = {
    "vdd": {"supply", "voltage"}, "vddio": {"supply", "voltage"},
    "vcc": {"supply", "voltage"}, "vbat": {"supply", "voltage"},
}

STATUS_VERIFIED = "VERIFIED"
STATUS_FOUND = "FOUND"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_AMBIGUOUS_MISSING_CONDITION = "AMBIGUOUS_MISSING_CONDITION"
STATUS_NOT_FOUND = "NOT_FOUND"


def tokenize(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def structural_check(query, cand: Candidate):
    """FAIL / PASS / UNKNOWN, tagged with the confidence tier that produced
    it. A FAIL or PASS derived only from Confidence.UNVERIFIED evidence is
    NOT allowed to unilaterally win against a conflicting same-parameter
    candidate -- see the uncertainty guard in extract_parameter."""
    is_restricted_query = any(m in query.lower() for m in RESTRICTED_QUERY_MARKERS)
    section = cand.section
    confidence = cand.section_confidence
    if not section:
        return "UNKNOWN", Confidence.NONE.value
    if section == "absolute_max" and not is_restricted_query:
        return "FAIL", confidence
    if section in ("operating", "electrical"):
        return "PASS", confidence
    return "UNKNOWN", confidence


def _is_clean_numeric(v):
    """Accepts signed decimals and real-world tolerance notation using +/-
    or the unicode +/- and vulgar-fraction glyphs (e.g. '\u00b12', '\u00b1\u00bd') --
    confirmed as legitimate real datasheet content (DS18B20's Thermometer
    Error row), not contamination. Requires at least one digit or fraction
    glyph so a bare/empty sign never counts as a value."""
    if not v or not NUM_RE.match(v):
        return False
    return any(ch.isdigit() for ch in v) or any(ch in "\u00bd\u2153\u2154\u00bc\u00be" for ch in v)


def value_quality(cand: Candidate):
    problems, status = [], "ok"
    for name, v in [("min", cand.min_val), ("typ", cand.typ_val), ("max", cand.max_val)]:
        if not v:
            continue
        if _is_clean_numeric(v) or FORMULA_RE.match(v):
            continue
        problems.append(f"{name}={v!r} not a clean number or known formula pattern")
        status = "malformed"
    if not (cand.min_val or cand.typ_val or cand.max_val):
        problems.append("no numeric value present at all")
        status = "malformed"
    return status, problems


def evidence_score(query, cand: Candidate):
    q_tokens = tokenize(query)
    concept_terms = SYMBOL_CONCEPT_TERMS.get(cand.symbol.lower(), set())
    label_tokens = tokenize(cand.detected_parameter) | tokenize(cand.symbol) | concept_terms
    condition_tokens = tokenize(cand.condition)
    overlap = q_tokens & label_tokens
    extra = label_tokens - q_tokens
    missing = q_tokens - label_tokens - condition_tokens
    score = 2.0*len(overlap) - 1.5*len(extra) - 1.0*len(missing)
    if cand.symbol and cand.symbol.lower() in q_tokens:
        score += 3.0
    if q_tokens and (q_tokens & condition_tokens):
        score += 1.0
    return score


def dedup(candidates: List[Candidate]):
    seen = {}
    for c in candidates:
        key = (c.detected_parameter.strip().lower(), c.symbol.strip().lower(),
               c.condition.strip().lower(), c.min_val, c.typ_val, c.max_val, c.unit)
        seen.setdefault(key, c)
    return list(seen.values())


@dataclass
class Trace:
    """Section 22's explainable internal trace -- not shown to the end user
    by default, available for debugging/evaluation."""
    steps: List[str] = field(default_factory=list)

    def log(self, step):
        self.steps.append(step)


@dataclass
class Decision:
    status: str
    accepted: List[Candidate] = field(default_factory=list)
    rejected: List[tuple] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)
    notes: str = ""
    trace: Trace = field(default_factory=Trace)


def _group_key(c: Candidate) -> str:
    """Parameter identity for grouping/ambiguity decisions. The reference
    designator (symbol) is the more reliable identity signal in engineering
    datasheets than the free-text label -- confirmed necessary on a real
    table (nRF24L01+ Table 3) where the only "parameter" column is actually
    a combined "Parameter (condition)" field, so two rows for the same real
    parameter (VDD) get different label text ("Supply voltage" vs "Supply
    voltage if input signals >3.6V") purely because the qualifier is
    embedded in that shared column. Falls back to label text when no
    symbol was extracted (tables with no Symbol column at all)."""
    return c.symbol.strip().lower() or c.detected_parameter.strip().lower()


def extract_parameter(candidates: List[Candidate], query: str) -> Decision:
    trace = Trace()
    trace.log(f"QUERY: {query!r}, {len(candidates)} raw candidates")
    candidates = dedup(candidates)
    trace.log(f"after dedup: {len(candidates)} candidates")

    scored, rejected = [], []
    for c in candidates:
        struct, confidence = structural_check(query, c)
        trace.log(f"candidate {c.detected_parameter!r}/{c.symbol!r} p{c.page}: "
                   f"structural={struct} confidence={confidence}")
        if struct == "FAIL":
            rejected.append((c, f"structural ({confidence}): negative-selection rejection"))
            continue
        quality, problems = value_quality(c)
        if quality == "malformed":
            rejected.append((c, f"malformed value: {'; '.join(problems)}"))
            continue
        score = evidence_score(query, c)
        trace.log(f"  evidence_score={score:.1f}")
        if score <= 0:
            rejected.append((c, f"evidence score too low ({score:.1f})"))
            continue
        scored.append((c, struct, confidence, score, quality))

    if not scored:
        trace.log("no candidate survived -> NOT_FOUND")
        return Decision(STATUS_NOT_FOUND, rejected=rejected, trace=trace,
                         notes="No candidate cleared both the structural check and a positive evidence score.")

    scored.sort(key=lambda x: -x[3])
    top_score = scored[0][3]
    top_tier = [s for s in scored if top_score - s[3] <= 2.0]
    distinct_params = {_group_key(s[0]) for s in top_tier}

    ranges_disagree = len({(s[0].min_val, s[0].typ_val, s[0].max_val) for s in top_tier}) > 1
    conditions_distinguish = len({s[0].condition.strip().lower() for s in top_tier
                                    if s[0].condition.strip()}) == len(top_tier)
    # Table/page identity: same-symbol candidates from DIFFERENT pages are a
    # genuine cross-table collision (plain AMBIGUOUS -- we may not even be
    # looking at the right table for one of them). Same-symbol candidates
    # from the SAME page are the narrower "this table has two rows for the
    # same parameter and nothing in the condition explains why they differ"
    # case (AMBIGUOUS_MISSING_CONDITION), per the spec's own definition
    # ("multiple candidates belong to the SAME valid table"). Conflating
    # these was a real regression caught by
    # test_mislabeled_header_cropped_call_is_ambiguous_not_confidently_wrong
    # when symbol-based grouping was introduced to fix a different real bug
    # (see _group_key) -- fixed here by requiring same-page agreement too.
    same_table = len({s[0].page for s in top_tier}) == 1

    # AMBIGUOUS_MISSING_CONDITION fires whenever nothing in the condition
    # text explains why same-parameter candidates disagree in value --
    # regardless of whether the section/table identity itself was verified.
    # (Earlier version gated this on "not all_verified_pass", which
    # incorrectly let the SAME-table, blank-condition case -- two real rows
    # from one correctly-identified Operating Conditions table -- through
    # as a confident FOUND. That was the exact residual gap named after the
    # previous test round; fixed here, confirmed by
    # test_split_condition_same_table_flags_missing_condition.)
    if (len(distinct_params) == 1 and ranges_disagree and len(top_tier) > 1
            and not conditions_distinguish and same_table):
        trace.log("-> AMBIGUOUS_MISSING_CONDITION: same parameter, conflicting values, "
                   "no distinguishing condition text")
        return Decision(
            STATUS_AMBIGUOUS_MISSING_CONDITION,
            accepted=[s[0] for s in top_tier], rejected=rejected, trace=trace,
            notes=("Multiple conflicting values found for the same parameter but distinguishing "
                   "condition information is unavailable. Not resolved automatically."),
        )

    if len(distinct_params) > 1:
        trace.log("-> AMBIGUOUS: distinct parameters tied in top tier")
        return Decision(STATUS_AMBIGUOUS, accepted=[s[0] for s in top_tier], rejected=rejected, trace=trace)

    # Same symbol, but from different pages/tables, with conflicting values
    # and nothing to distinguish them: a genuine cross-table collision (this
    # is exactly the real mislabeled-header case -- we cannot safely assume
    # either table is the right one). Must not fall through to a confident
    # FOUND just because they share a group key.
    if len(distinct_params) == 1 and ranges_disagree and len(top_tier) > 1 and not same_table:
        trace.log("-> AMBIGUOUS: same symbol but different tables/pages, conflicting values")
        return Decision(STATUS_AMBIGUOUS, accepted=[s[0] for s in top_tier], rejected=rejected, trace=trace,
                         notes="Same parameter symbol found on different pages/tables with conflicting "
                               "values; cannot safely determine which table is authoritative.")

    winners = [s for s in scored if _group_key(s[0]) in distinct_params]
    accepted = [w[0] for w in winners]
    caveats = [c.footnote_text for c in accepted if c.footnote_text]
    trace.log(f"-> FOUND: {len(accepted)} accepted candidate(s)")
    return Decision(STATUS_FOUND, accepted=accepted, rejected=rejected, caveats=caveats, trace=trace)
