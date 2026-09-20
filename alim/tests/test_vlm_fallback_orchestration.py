"""
Tests that api.extract() actually wires the VLM fallback path -- found to
be missing (accepted a vlm_provider parameter, never called it) while
preparing the Qualcomm integration. Uses a fixture provider; no live
model involved. This is core engine orchestration, not Qualcomm-specific,
hence its own file rather than test_qualcomm_integration.py.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alim.api.extract import extract
from alim.vlm.interface import VLMPerceptionProvider
from alim.candidates.build import Candidate

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class _FixtureProvider(VLMPerceptionProvider):
    def __init__(self, response_by_page=None):
        self.calls = []
        self._response_by_page = response_by_page or {}

    def perceive(self, pdf_path, page_number, query):
        self.calls.append((page_number, query))
        return self._response_by_page.get(page_number, [])


def _require_fixture(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        import pytest
        pytest.skip("real PDF fixture not present -- run fetch_fixtures.py first")
    return path


def test_no_provider_behavior_is_unchanged():
    """Default (no vlm_provider) must be identical to structural-only
    extraction -- this is what every prior verified result depends on."""
    path = _require_fixture("LM35.pdf")
    r = extract(path, "supply voltage")
    assert r["status"] == "SCHEMA_UNKNOWN"
    assert "vlm_calls" not in r


def test_vlm_fallback_resolves_a_structurally_refused_table():
    """LM35's real device-variant table is correctly refused by the
    structural pipeline. A configured VLM provider supplying evidence for
    those exact pages must be consulted, and its candidates must reach the
    same unchanged decision core."""
    path = _require_fixture("LM35.pdf")
    good_candidate = Candidate(detected_parameter="Supply Voltage", symbol="VCC",
                                 min_val="4", max_val="30", unit="V",
                                 section="operating", section_confidence="VERIFIED", page=3)
    provider = _FixtureProvider(response_by_page={3: [good_candidate], 4: []})
    r = extract(path, "supply voltage", vlm_provider=provider)
    assert len(provider.calls) >= 1, "VLM provider was never invoked"
    assert r["status"] == "VERIFIED"
    assert r["results"][0]["value"] == "4\u201330"
    assert "vlm_calls" in r and len(r["vlm_calls"]) == len(provider.calls)


def test_vlm_only_called_for_pages_with_unresolved_tables_not_every_page():
    """The whole point of running structural extraction first: a VLM must
    not be invoked for pages that already resolved successfully."""
    path = _require_fixture("nRF24L01P.PDF")
    provider = _FixtureProvider()
    extract(path, "operating supply voltage", vlm_provider=provider)
    called_pages = {p for p, _ in provider.calls}
    # Pages 12/13 (the real Absolute-Max/Operating tables) resolve structurally
    # and must NOT trigger a VLM call for this query's document.
    assert 13 not in called_pages, "a page that resolved structurally should not need the VLM"


def test_vlm_error_does_not_crash_extraction():
    """A VLM call that raises must be treated as perception noise, not a
    fatal error -- the rest of the extraction should still complete."""
    path = _require_fixture("LM35.pdf")

    class _BrokenProvider(VLMPerceptionProvider):
        def perceive(self, pdf_path, page_number, query):
            raise RuntimeError("simulated model backend failure")

    r = extract(path, "supply voltage", vlm_provider=_BrokenProvider())
    assert r["status"] in ("SCHEMA_UNKNOWN", "NOT_FOUND")
    assert any("error" in c for c in r.get("vlm_calls", []))
