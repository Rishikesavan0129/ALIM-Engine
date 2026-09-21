"""
Real finding: on the real nRF24L01+ datasheet (78 pages), 77 pages have
at least one table-shaped region the schema classifier doesn't recognize.
Without page ranking, escalating to a VLM after a failed structural pass
would call it on up to 77 pages for one query. These tests confirm the
fix actually limits calls and actually targets the right page, not just
"fewer pages, any pages."
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alim.api.extract import extract
from alim.vlm.interface import VLMPerceptionProvider

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class _CountingProvider(VLMPerceptionProvider):
    def __init__(self):
        self.pages_called = []

    def perceive(self, pdf_path, page_number, query):
        self.pages_called.append(page_number)
        return []


def _require_fixture(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        import pytest
        pytest.skip("real PDF fixture not present -- run fetch_fixtures.py first")
    return path


def test_vlm_calls_capped_well_below_total_unsupported_pages():
    path = _require_fixture("nRF24L01P.PDF")
    provider = _CountingProvider()
    extract(path, "crystal oscillator frequency tolerance", vlm_provider=provider)
    assert len(provider.pages_called) <= 5, (
        f"expected calls capped at max_vlm_pages default (5), got {len(provider.pages_called)}")


def test_page_ranking_actually_finds_the_relevant_real_page():
    """Page 19 is the real Crystal oscillator characteristics section on
    this real datasheet (Crystal Frequency, Tolerance, Load capacitance).
    A ranking that just returned pages in document order would very
    likely miss it within the first 5 of 77."""
    path = _require_fixture("nRF24L01P.PDF")
    provider = _CountingProvider()
    extract(path, "crystal oscillator frequency tolerance", vlm_provider=provider)
    assert 19 in provider.pages_called, (
        f"expected the real crystal-oscillator page (19) in the targeted set, got {provider.pages_called}")


def test_max_vlm_pages_is_respected():
    path = _require_fixture("nRF24L01P.PDF")
    provider = _CountingProvider()
    extract(path, "crystal oscillator frequency tolerance", vlm_provider=provider, max_vlm_pages=2)
    assert len(provider.pages_called) <= 2
