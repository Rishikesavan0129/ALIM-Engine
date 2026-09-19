"""
The 10 decision-layer scenarios from prior sessions, as permanent regression
tests. These use hand-built Candidate objects (standing in for either a
structural or VLM perception source) so this file tests decision.core in
isolation from ingestion -- exactly the separation the spec requires
("only change the decision core when a test demonstrates a genuine
decision-layer failure").
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alim.candidates.build import Candidate
from alim.decision.core import extract_parameter
from alim.schema.classify import Confidence


def cand(**kw):
    kw.setdefault("section_confidence", Confidence.NONE.value)
    return Candidate(**kw)


def test_mislabeled_header_full_context_rejects_absolute_max():
    cands = [
        cand(detected_parameter="VDD", symbol="VDD", min_val="-0.3", max_val="3.6", unit="V",
             section="absolute_max", section_confidence=Confidence.VERIFIED.value, page=12),
        cand(detected_parameter="Supply voltage", symbol="VDD", min_val="1.9", typ_val="3.0", max_val="3.6",
             unit="V", section="operating", section_confidence=Confidence.VERIFIED.value, page=13),
    ]
    d = extract_parameter(cands, "operating supply voltage")
    assert d.status == "FOUND"
    assert d.accepted[0].min_val == "1.9"


def test_mislabeled_header_cropped_call_is_ambiguous_not_confidently_wrong():
    cands = [
        cand(detected_parameter="VDD", symbol="VDD", min_val="-0.3", max_val="3.6", unit="V",
             section="operating", section_confidence=Confidence.UNVERIFIED.value, page=12),
        cand(detected_parameter="Supply voltage", symbol="VDD", min_val="1.9", typ_val="3.0", max_val="3.6",
             unit="V", section="operating", section_confidence=Confidence.UNVERIFIED.value, page=13),
    ]
    d = extract_parameter(cands, "operating supply voltage")
    assert d.status == "AMBIGUOUS", "must not silently accept the abs-max value with identical, unverified section text"


def test_duplicated_candidates_collapse_to_one():
    base = dict(detected_parameter="Supply voltage", symbol="VDD", min_val="1.9", typ_val="3.0", max_val="3.6",
                unit="V", section="operating", section_confidence=Confidence.VERIFIED.value, page=13)
    d = extract_parameter([cand(**base, source_region="pass1"), cand(**base, source_region="pass2")],
                           "operating supply voltage")
    assert d.status == "FOUND"
    assert len(d.accepted) == 1


def test_split_condition_same_table_flags_missing_condition():
    cands = [
        cand(detected_parameter="Supply voltage", symbol="VDD", min_val="1.9", typ_val="3.0", max_val="3.6",
             unit="V", section="operating", section_confidence=Confidence.VERIFIED.value, page=13),
        cand(detected_parameter="Supply voltage", symbol="VDD", min_val="2.7", typ_val="3.0", max_val="3.3",
             unit="V", section="operating", section_confidence=Confidence.VERIFIED.value, page=13, condition=""),
    ]
    d = extract_parameter(cands, "operating supply voltage")
    assert d.status == "AMBIGUOUS_MISSING_CONDITION", (
        "two same-parameter candidates from the same verified table, with blank condition text and "
        "conflicting values, must be flagged explicitly -- not silently merged or picked")
    assert len(d.accepted) == 2


def test_decoy_rail_does_not_win():
    cands = [
        cand(detected_parameter="Supply Voltage", symbol="VDD", min_val="1.71", typ_val="1.8", max_val="3.6",
             unit="V", section="electrical", section_confidence=Confidence.VERIFIED.value, page=5),
        cand(detected_parameter="Interface Supply Voltage", symbol="VDDIO", min_val="1.2", typ_val="1.8",
             max_val="3.6", unit="V", section="electrical", section_confidence=Confidence.VERIFIED.value, page=5),
        cand(detected_parameter="Analog Supply Voltage", symbol="AVDD", min_val="2.4", typ_val="2.8", max_val="3.6",
             unit="V", section="electrical", section_confidence=Confidence.VERIFIED.value, page=5),
    ]
    d = extract_parameter(cands, "interface supply voltage")
    assert d.status == "FOUND"
    assert d.accepted[0].symbol == "VDDIO"


def test_missing_section_field_flags_uncertain():
    cands = [
        cand(detected_parameter="Input-to-output differential voltage", symbol="VI-VO", max_val="40", unit="V",
             section=""),
        cand(detected_parameter="Input-to-output differential voltage", symbol="VI-VO", min_val="3", max_val="40",
             unit="V", section="operating", section_confidence=Confidence.VERIFIED.value),
    ]
    d = extract_parameter(cands, "operating input to output differential voltage")
    assert d.status == "AMBIGUOUS_MISSING_CONDITION"


def test_footnote_is_preserved_not_dropped():
    cands = [cand(detected_parameter="PWM output period", symbol="PWMT,def", typ_val="1.024", unit="ms",
                   condition="Factory default", section="electrical",
                   section_confidence=Confidence.VERIFIED.value,
                   footnote_text="Note 1: values apply only in PWM mode.")]
    d = extract_parameter(cands, "PWM output period")
    assert d.status == "FOUND"
    assert d.caveats == ["Note 1: values apply only in PWM mode."]


def test_multi_condition_values_all_preserved():
    cands = [cand(detected_parameter="Supply current", symbol="IDD,H", condition=f"OSR x{n}/x1",
                   typ_val=str(v), unit="uA", section="electrical",
                   section_confidence=Confidence.VERIFIED.value, page=8)
             for n, v in [(1, 1.8), (2, 2.5), (4, 3.8)]]
    d = extract_parameter(cands, "supply current")
    assert d.status == "FOUND"
    assert len(d.accepted) == 3


def test_malformed_value_rejected_not_crashed():
    cands = [cand(detected_parameter="Supply Voltage", symbol="VDD", min_val="l.71", max_val="3.6", unit="V",
                   section="electrical", section_confidence=Confidence.VERIFIED.value)]
    d = extract_parameter(cands, "supply voltage")
    assert d.status == "NOT_FOUND"
    assert "malformed" in d.rejected[0][1]


def test_genuinely_absent_parameter_returns_not_found():
    cands = [cand(detected_parameter="Supply Voltage", symbol="VDD", min_val="1.71", max_val="3.6", unit="V",
                   section="electrical", section_confidence=Confidence.VERIFIED.value)]
    d = extract_parameter(cands, "power factor correction ripple")
    assert d.status == "NOT_FOUND"
