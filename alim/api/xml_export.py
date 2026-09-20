"""
Converts an extract() result dict into a simple, readable XML string --
meant for handing a result (found, ambiguous, or empty) to another LLM or
downstream tool without it needing to understand ALIM's dict shape. Every
field ALIM actually produced is included; nothing is invented to fill out
the schema.

Usage:
    result = extract(pdf_path, query, include_all_evidence=True)
    print(to_xml(result))
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom


def _add_evidence_item(parent, tag, item):
    el = ET.SubElement(parent, tag)
    for key in ("parameter", "symbol", "value", "unit", "condition", "page", "outcome", "reason"):
        if key in item and item[key] is not None:
            child = ET.SubElement(el, key)
            child.text = str(item[key])
    if "evidence" in item:
        ev = ET.SubElement(el, "evidence")
        for k, v in item["evidence"].items():
            if v is None:
                continue
            c = ET.SubElement(ev, k)
            c.text = str(v)
    return el


def to_xml(result: dict, pretty: bool = True) -> str:
    root = ET.Element("alim_result")

    ET.SubElement(root, "parameter").text = str(result.get("parameter", ""))
    ET.SubElement(root, "status").text = str(result.get("status", ""))
    if result.get("reason"):
        ET.SubElement(root, "reason").text = str(result["reason"])

    if result.get("results"):
        results_el = ET.SubElement(root, "results")
        for item in result["results"]:
            _add_evidence_item(results_el, "result", item)

    if result.get("candidates"):
        cands_el = ET.SubElement(root, "candidates")
        for item in result["candidates"]:
            _add_evidence_item(cands_el, "candidate", item)

    if result.get("caveats"):
        caveats_el = ET.SubElement(root, "caveats")
        for c in result["caveats"]:
            ET.SubElement(caveats_el, "caveat").text = str(c)

    if result.get("all_evidence"):
        evidence_el = ET.SubElement(root, "all_evidence")
        evidence_el.set("note", "everything the engine considered for this query, matched or not")
        for item in result["all_evidence"]:
            _add_evidence_item(evidence_el, "candidate", item)

    if result.get("unsupported_tables"):
        unsup_el = ET.SubElement(root, "unsupported_tables")
        unsup_el.set("note", "table-shaped regions found but not confidently classified")
        for t in result["unsupported_tables"]:
            t_el = ET.SubElement(unsup_el, "table")
            for k, v in t.items():
                ET.SubElement(t_el, k).text = str(v)

    if "unresolved_table_count" in result:
        ET.SubElement(root, "unresolved_table_count").text = str(result["unresolved_table_count"])

    if result.get("vlm_calls"):
        vlm_el = ET.SubElement(root, "vlm_calls")
        for call in result["vlm_calls"]:
            c_el = ET.SubElement(vlm_el, "call")
            for k, v in call.items():
                ET.SubElement(c_el, k).text = str(v)

    xml_str = ET.tostring(root, encoding="unicode")
    if not pretty:
        return xml_str
    return minidom.parseString(xml_str).toprettyxml(indent="  ").replace(
        '<?xml version="1.0" ?>\n', "")
