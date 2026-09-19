"""
Two separate classification jobs, deliberately kept apart:

1. Table SHAPE (what schema this grid follows -- Min/Typ/Max? single-value?
   device-variant columns? a register bit-field table?). Determines whether
   row/value extraction is even attempted.

2. Section IDENTITY (is this an Absolute-Maximum-Ratings table, an
   Operating-Conditions table, ...). Determines negative-selection outcome.
   Carries an explicit confidence tier because the evidence sources for it
   are NOT equally reliable -- proven on a real, published datasheet
   (Nordic nRF24L01+, Table 2) where the table's own header row read
   "Operating conditions" while the table was actually Absolute Maximum
   Ratings; only the caption below it was correct.

Honest scope: this implements 6 of the 14 schema shapes named in the spec
(spec_table, single_value_table, device_variant_unsupported,
merged_header_unsupported, bitfield_unsupported, unknown_unsupported).
Narrative (non-tabular) specifications, condition-in-separate-column
layouts, and cross-page continuation tables are NOT yet distinguished --
see LIMITATIONS.md. That is a stated gap, not a silent one: any table this
classifier can't confidently place returns an explicit refusal schema
rather than being forced through spec_table extraction.
"""
import re
from enum import Enum


class Confidence(str, Enum):
    VERIFIED = "VERIFIED"                    # from a caption, e.g. "Table 2. Absolute maximum ratings"
    STRONGLY_SUPPORTED = "STRONGLY_SUPPORTED"  # from a preceding numbered section heading, no caption
    SUPPORTED = "SUPPORTED"                  # reserved: a second corroborating signal beyond caption/heading
                                              # (e.g. cross-document agreement) -- NOT currently produced;
                                              # included for API compatibility with the spec, not faked.
    UNVERIFIED = "UNVERIFIED"                # from the table's OWN header/section text only -- proven unreliable
    AMBIGUOUS = "AMBIGUOUS"                  # caption/heading and header text actively disagree
    NONE = "NONE"                            # nothing classifiable at all


FIELD_ALIASES = {
    "parameter": "parameter", "symbol": "symbol",
    "condition": "condition", "test conditions": "condition", "conditions": "condition",
    "parameter (condition)": "parameter_and_condition",
    "min": "min", "min.": "min", "minimum": "min",
    "typ": "typ", "typ.": "typ", "typical": "typ",
    "max": "max", "max.": "max", "maximum": "max",
    "value": "value", "rating": "value", "typical value": "value",
    "unit": "unit", "units": "unit", "notes": "notes",
}


def normalize_header_cell(text):
    if text is None:
        return ""
    text = text.strip()
    if "\n" not in text:
        return text
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return " ".join(lines)


def classify_table_shape(header_row):
    cells = [normalize_header_cell(c) for c in header_row]
    non_empty = [c for c in cells if c]
    if not cells:
        return "unknown_unsupported"
    empty_ratio = 1 - (len(non_empty) / len(cells))
    if empty_ratio > 0.35 and len(cells) >= 6:
        return "merged_header_unsupported"
    lower = [c.lower() for c in non_empty]
    if "bit" in " ".join(lower) and "field" in " ".join(lower) and "description" in " ".join(lower):
        return "bitfield_unsupported"
    known = sum(1 for c in lower if c in FIELD_ALIASES)
    numeric_hits = sum(1 for c in lower if FIELD_ALIASES.get(c) in ("min", "typ", "max"))
    value_hits = sum(1 for c in lower if FIELD_ALIASES.get(c) == "value")
    if known < max(2, len(non_empty) * 0.5):
        return "device_variant_unsupported"
    if numeric_hits > 0:
        return "spec_table"
    if value_hits > 0:
        return "single_value_table"
    return "device_variant_unsupported"


SECTION_KEYWORDS = {
    "absolute_max": ["absolute maximum"],
    "operating": ["recommended operating", "operating condition"],
    "electrical": ["electrical characteristic", "electrical specification"],
}


def classify_section_text(text):
    if not text:
        return None
    t = text.lower()
    for label, keywords in SECTION_KEYWORDS.items():
        if any(k in t for k in keywords):
            return label
    return None


def classify_section(caption, preceding_heading, header_text):
    """Returns (section_label, confidence). This is the function that
    encodes the caption-over-header trust order established on real data."""
    caption_class = classify_section_text(caption)
    if caption_class is not None:
        return caption_class, Confidence.VERIFIED

    heading_class = classify_section_text(preceding_heading)
    if heading_class is not None:
        return heading_class, Confidence.STRONGLY_SUPPORTED

    header_class = classify_section_text(header_text)
    if header_class is not None:
        return header_class, Confidence.UNVERIFIED

    return None, Confidence.NONE
