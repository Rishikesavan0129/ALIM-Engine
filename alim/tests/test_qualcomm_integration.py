"""
Tests the Qualcomm integration layer: VLM JSON evidence -> Candidate ->
existing ALIM decision core. Uses a fixture `generate_fn` standing in for
a real model call -- there is no live Qualcomm VLM in this environment (no
network route to a model endpoint, no Snapdragon NPU in this sandbox). Each
fixture's JSON represents a plausible real model response for the
scenario named; these are integration/mapping tests, not evidence that a
real Qwen3-VL-4B-Instruct call would produce this exact JSON. See
docs/QUALCOMM.md for what remains unverified against a live model.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alim.integrations.qualcomm.provider import parse_evidence_to_candidates, QualcommVLMProvider
from alim.decision.core import extract_parameter
from alim.schema.classify import Confidence


def decide(raw_json, query, page=0):
    cands = parse_evidence_to_candidates(raw_json, default_page=page)
    return cands, extract_parameter(cands, query)


# 1. Operating vs Absolute Maximum (real nRF24L01+ values, VLM-perceived)
def test_operating_vs_absolute_max():
    raw = """[
      {"section": "Absolute maximum ratings", "table_caption": "Table 2. Absolute maximum ratings",
       "parameter": "VDD", "symbol": "VDD", "min": "-0.3", "max": "3.6", "unit": "V", "page": 12, "uncertain": false},
      {"section": "Operating conditions", "table_caption": "Table 3. Operating conditions",
       "parameter": "Supply voltage", "symbol": "VDD", "min": "1.9", "typ": "3.0", "max": "3.6", "unit": "V",
       "page": 13, "uncertain": false}
    ]"""
    _, d = decide(raw, "operating supply voltage")
    assert d.status == "FOUND"
    assert d.accepted[0].min_val == "1.9"


# 2. VDD vs VDDIO
def test_vdd_vs_vddio():
    raw = """[
      {"section": "Electrical Characteristics", "table_caption": "Table 1. Electrical characteristics",
       "parameter": "Supply Voltage", "symbol": "VDD", "min": "1.71", "typ": "1.8", "max": "3.6", "unit": "V", "page": 5, "uncertain": false},
      {"section": "Electrical Characteristics", "table_caption": "Table 1. Electrical characteristics",
       "parameter": "Interface Supply Voltage", "symbol": "VDDIO", "min": "1.2", "typ": "1.8", "max": "3.6", "unit": "V", "page": 5, "uncertain": false}
    ]"""
    _, d = decide(raw, "interface supply voltage")
    assert d.status == "FOUND"
    assert d.accepted[0].symbol == "VDDIO"


# 3. Multiple values under different conditions (must all be preserved)
def test_multiple_conditions_preserved():
    raw = """[
      {"section": "Electrical Characteristics", "table_caption": "Table 1.",
       "parameter": "Supply current", "symbol": "IDD", "condition": "OSR x1/x1", "typ": "1.8", "unit": "uA", "page": 8, "uncertain": false},
      {"section": "Electrical Characteristics", "table_caption": "Table 1.",
       "parameter": "Supply current", "symbol": "IDD", "condition": "OSR x2/x1", "typ": "2.5", "unit": "uA", "page": 8, "uncertain": false}
    ]"""
    _, d = decide(raw, "supply current")
    assert d.status == "FOUND"
    assert len(d.accepted) == 2


# 4. Missing parameter -- VLM correctly returns an empty array
def test_missing_parameter_empty_evidence():
    _, d = decide("[]", "power factor correction ripple")
    assert d.status == "NOT_FOUND"


# 5. Similar but incorrect parameter (decoy rail)
def test_similar_but_incorrect_parameter():
    raw = """[
      {"section": "Electrical Characteristics", "table_caption": "Table 1.",
       "parameter": "Interface Supply Voltage", "symbol": "VDDIO", "min": "1.2", "max": "3.6", "unit": "V", "page": 5, "uncertain": false},
      {"section": "Electrical Characteristics", "table_caption": "Table 1.",
       "parameter": "Analog Supply Voltage", "symbol": "AVDD", "min": "2.4", "max": "3.6", "unit": "V", "page": 5, "uncertain": false}
    ]"""
    _, d = decide(raw, "interface supply voltage")
    assert d.status == "FOUND"
    assert d.accepted[0].symbol == "VDDIO"


# 6. Footnote-modified value must reach the final result
def test_footnote_modified_value():
    raw = """[
      {"section": "Electrical Specifications", "table_caption": "Table 6. Electrical specifications",
       "parameter": "PWM output period", "symbol": "PWMT", "condition": "Factory default", "typ": "1.024", "unit": "ms",
       "footnote_text": "Note 1: values apply only in PWM mode, not SMBus mode.", "page": 6, "uncertain": false}
    ]"""
    _, d = decide(raw, "PWM output period")
    assert d.status == "FOUND"
    assert d.caveats == ["Note 1: values apply only in PWM mode, not SMBus mode."]


# 7. Symbol-only parameter (no descriptive label at all)
def test_symbol_only_parameter():
    raw = """[
      {"section": "Electrical Characteristics", "table_caption": "Table 1.",
       "parameter": null, "symbol": "VDD", "min": "1.71", "max": "3.6", "unit": "V", "page": 5, "uncertain": false}
    ]"""
    cands, d = decide(raw, "supply voltage")
    assert len(cands) == 1
    assert d.status == "FOUND"


# 8. Formula-valued limit -- must be preserved as printed text, not computed
def test_formula_valued_limit_preserved_as_text():
    raw = """[
      {"section": "Electrical Specifications", "table_caption": "Table 6.",
       "parameter": "Output high Level", "symbol": "PWMHI", "condition": "Isource = 2 mA",
       "min": "VDD-0.2", "unit": "V", "page": 6, "uncertain": false}
    ]"""
    cands, _ = decide(raw, "output high level")
    assert cands[0].min_val == "VDD-0.2"


# 9. Multiple legitimate candidates with genuinely equivalent scores -> AMBIGUOUS,
# not a coin-flip pick (mislabeled-header case, evidence scope weak on both sides)
def test_ambiguous_when_uncertain_and_conflicting():
    raw = """[
      {"section": "Operating conditions", "parameter": "VDD", "symbol": "VDD",
       "min": "-0.3", "max": "3.6", "unit": "V", "page": 12, "uncertain": true},
      {"section": "Operating conditions", "parameter": "Supply voltage", "symbol": "VDD",
       "min": "1.9", "max": "3.6", "unit": "V", "page": 13, "uncertain": true}
    ]"""
    _, d = decide(raw, "operating supply voltage")
    assert d.status == "AMBIGUOUS", (
        "both readings are self-reported uncertain with conflicting values and no caption; "
        "must not confidently pick one")


# 10. Unfamiliar/malformed evidence: model wrapped JSON in prose despite instructions
def test_malformed_json_wrapped_in_prose_does_not_crash():
    raw = 'Here is the extracted data:\n[{"parameter": "VDD", "symbol": "VDD", "min": "1.71", "max": "3.6", "unit": "V", "page": 5, "uncertain": false}]\nLet me know if you need more.'
    cands, d = decide(raw, "supply voltage")
    assert len(cands) == 1
    assert d.status == "FOUND"


# 11. Completely unparseable output -> empty evidence, not a crash
def test_completely_unparseable_output():
    cands, d = decide("I cannot see any tables on this page.", "supply voltage")
    assert cands == []
    assert d.status == "NOT_FOUND"


# 12. Uncertain flag downgrades confidence even when a caption is present
def test_uncertain_flag_downgrades_verified_to_unverified():
    raw = """[{"section": "Operating conditions", "table_caption": "Table 3. Operating conditions",
                "parameter": "Supply voltage", "symbol": "VDD", "min": "1.9", "max": "3.6", "unit": "V",
                "page": 13, "uncertain": true}]"""
    cands = parse_evidence_to_candidates(raw)
    assert cands[0].section_confidence == Confidence.UNVERIFIED.value


def test_prompt_instructs_splitting_plain_text_ranges():
    """Real finding: a model returned correct labels (section, parameter,
    symbol) but null min/max/typ, with uncertain=false, for a real
    Absolute Maximum Ratings row expressed as a plain '-0.5 VDC to +18 VDC'
    range rather than separate Min/Max columns -- the prompt had a rule for
    formula-relative bounds but none for this much more common plain-range
    case, so the model likely didn't know which field to put a two-sided
    range into and defaulted to null rather than guess. This just checks
    the instruction is actually present, not that a live model follows it
    (that requires the real model, not available in this environment)."""
    from alim.integrations.qualcomm.schema import build_prompt
    prompt = build_prompt("supply voltage")
    assert "min=\"-0.5\", max=\"18\"" in prompt or "-0.5 VDC to +18 VDC" in prompt


def test_correctly_split_range_evidence_reaches_a_decision():
    """If the model DOES follow the new instruction and splits a plain
    range into separate min/max, confirm that evidence flows all the way
    through to a real accepted result -- not just that the prompt asks
    for it."""
    raw = """[{"section": "Recommended Operating Conditions", "table_caption": "Table 3. Operating conditions",
               "parameter": "DC Supply Voltage", "symbol": "VDD", "condition": null,
               "min": "3", "max": "15", "unit": "VDC", "uncertain": false}]"""
    cands = parse_evidence_to_candidates(raw)
    assert cands[0].min_val == "3" and cands[0].max_val == "15"
    d = extract_parameter(cands, "supply voltage")
    assert d.status == "FOUND"
    assert d.accepted[0].min_val == "3"


def test_truncated_response_recovers_complete_leading_candidates():
    """Real finding: a real Qwen3-VL-4B-Instruct response was cut off by
    max_new_tokens partway through the 3rd of 3 candidates (verbose
    repeated footnote text ate the token budget). The first version of
    the parser dropped ALL 3 real candidates because the array never
    closed -- including the 2 real, complete, useful ones. This is the
    exact real truncated text that caused it, used verbatim."""
    raw = '''[
  {
    "section": "Absolute Maximum Ratings (Note 1)",
    "parameter": "DC Supply Voltage (VDD)",
    "min": "-0.5",
    "max": "18",
    "unit": "VDC",
    "footnote_text": "Note 1: text"
  },
  {
    "section": "Absolute Maximum Ratings (Note 1)",
    "parameter": "Input Voltage (VDD)",
    "min": "-0.5",
    "max": "18",
    "unit": "VDC",
    "footnote_text": "Note 1: text"
  },
  {
    "section": "Absolute Maximum Ratings (Note 1)",
    "parameter": "Storage Temperature (T'''
    cands = parse_evidence_to_candidates(raw, default_page=3)
    assert len(cands) == 2, f"expected the 2 complete leading candidates recovered, got {len(cands)}"
    assert cands[0].min_val == "-0.5" and cands[0].max_val == "18"
    assert cands[1].detected_parameter == "Input Voltage (VDD)"
    # the incomplete 3rd object must not appear at all, not even partially
    assert not any("Storage" in c.detected_parameter for c in cands)


def test_provider_end_to_end_with_fixture_backend():
    """The full VLMPerceptionProvider contract, exercised with a fixture
    generate_fn instead of a real model call. Confirms the provider slots
    into the existing interface without any changes to it."""
    def fixture_generate_fn(image_bytes, prompt):
        assert isinstance(image_bytes, (bytes, bytearray))
        assert "supply voltage" in prompt.lower()
        return '[{"parameter": "Supply voltage", "symbol": "VDD", "min": "1.9", "max": "3.6", "unit": "V", "uncertain": false}]'

    fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    pdf_path = os.path.join(fixtures_dir, "nRF24L01P.PDF")
    if not os.path.exists(pdf_path):
        import pytest
        pytest.skip("real PDF fixture not present -- run fetch_fixtures.py first")

    provider = QualcommVLMProvider(generate_fn=fixture_generate_fn)
    cands = provider.perceive(pdf_path, page_number=13, query="operating supply voltage")
    assert len(cands) == 1
    assert cands[0].min_val == "1.9"
