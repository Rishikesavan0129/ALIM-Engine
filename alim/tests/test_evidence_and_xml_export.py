"""
Tests the include_all_evidence option (never return an empty-handed
failure when the engine actually saw usable structure) and the XML
export helper.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alim.api.extract import extract
from alim.api.xml_export import to_xml

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _require_fixture(name):
    path = os.path.join(FIXTURES, name)
    if not os.path.exists(path):
        import pytest
        pytest.skip("real PDF fixture not present -- run fetch_fixtures.py first")
    return path


def test_not_found_still_returns_all_considered_evidence():
    path = _require_fixture("nRF24L01P.PDF")
    r = extract(path, "power factor correction ripple", include_all_evidence=True)
    assert r["status"] == "NOT_FOUND"
    assert len(r["all_evidence"]) > 0, "a genuinely absent query should still surface what WAS found"
    assert all("outcome" in e for e in r["all_evidence"])


def test_default_behavior_unchanged_without_the_flag():
    path = _require_fixture("nRF24L01P.PDF")
    r = extract(path, "power factor correction ripple")
    assert "all_evidence" not in r, "opt-in flag must not change default output shape"


def test_xml_export_on_a_found_result():
    path = _require_fixture("nRF24L01P.PDF")
    r = extract(path, "operating supply voltage")
    xml_str = to_xml(r)
    assert "<status>VERIFIED</status>" in xml_str or "<status>FOUND</status>" in xml_str
    assert "1.9" in xml_str


def test_xml_export_on_not_found_with_evidence():
    path = _require_fixture("nRF24L01P.PDF")
    r = extract(path, "power factor correction ripple", include_all_evidence=True)
    xml_str = to_xml(r)
    assert "<all_evidence" in xml_str
    assert xml_str.count("<candidate>") > 50  # this real document has ~130 considered candidates


def test_xml_export_is_well_formed():
    import xml.etree.ElementTree as ET
    path = _require_fixture("LM35.pdf")
    r = extract(path, "supply voltage", include_all_evidence=True)
    xml_str = to_xml(r)
    ET.fromstring(xml_str)  # raises if malformed
