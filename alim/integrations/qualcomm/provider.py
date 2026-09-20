"""
VLM JSON evidence -> alim.candidates.build.Candidate, and the
VLMPerceptionProvider implementation that plugs into ALIM's existing
decision core unchanged.

Backend-agnostic by design: QualcommVLMProvider takes a `generate_fn`
callable, `(image, prompt) -> raw_text`. Swap in a Hugging Face
transformers call, a GenieX CLI subprocess call, or (for tests) a fixture
function that returns pre-written JSON -- the parsing and safety rules
below are identical either way, which is the actual point: ALIM's
decision core never knows or cares which backend produced the evidence.
"""
import json
import re
from typing import Callable, List

from alim.candidates.build import Candidate
from alim.schema.classify import classify_section_text, Confidence
from alim.vlm.interface import VLMPerceptionProvider

GenerateFn = Callable[[object, str], str]


def _extract_json_array(raw_text: str) -> list:
    """Models occasionally wrap JSON in prose or code fences despite
    instructions not to. Try direct parse first, then fall back to
    extracting the first [...] span. Returns [] (not a crash) on failure --
    a VLM that returns garbage is perception noise, not a reason to raise."""
    raw_text = raw_text.strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return []


def _clean(v):
    """Normalizes the model's own null/None/"N/A"/"" spellings to "" so
    downstream Candidate logic (which uses falsy-string checks throughout)
    treats them uniformly. Never fills in a guessed value."""
    if v is None:
        return ""
    v = str(v).strip()
    if v.lower() in ("null", "none", "n/a", "na", "-", ""):
        return ""
    return v


def parse_evidence_to_candidates(raw_text: str, default_page: int = 0) -> List[Candidate]:
    items = _extract_json_array(raw_text)
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        parameter = _clean(item.get("parameter"))
        symbol = _clean(item.get("symbol"))
        if not parameter and not symbol:
            continue  # nothing to identify this candidate by -- drop, don't guess

        section_text = _clean(item.get("table_caption")) or _clean(item.get("section"))
        section_label = classify_section_text(section_text) if section_text else None
        is_caption = bool(_clean(item.get("table_caption")))
        uncertain = bool(item.get("uncertain", False))

        if section_label is None:
            confidence = Confidence.NONE.value
        elif uncertain:
            # The model itself flagged doubt about this reading. Never let a
            # self-reported-uncertain reading carry VERIFIED weight, even if
            # it came from what looks like a caption -- an uncertain OCR of
            # a caption is not the same evidence quality as a confident one.
            confidence = Confidence.UNVERIFIED.value
        else:
            confidence = Confidence.VERIFIED.value if is_caption else Confidence.STRONGLY_SUPPORTED.value

        candidates.append(Candidate(
            detected_parameter=parameter or symbol,
            symbol=symbol,
            condition=_clean(item.get("condition")),
            min_val=_clean(item.get("min")),
            typ_val=_clean(item.get("typ")),
            max_val=_clean(item.get("max")),
            unit=_clean(item.get("unit")),
            section=section_label or "",
            section_confidence=confidence,
            table_schema="vlm_perceived",
            page=item.get("page") or default_page,
            footnote_text=_clean(item.get("footnote_text")),
            source_region="vlm",
        ))
    return candidates


class QualcommVLMProvider(VLMPerceptionProvider):
    """Real implementation of the interface defined in alim.vlm.interface.
    Not tied to any specific runtime -- see qualcomm_alim_colab.ipynb for
    a Hugging Face transformers backend, and
    tests/test_qualcomm_integration.py for a fixture backend.

    Renders the requested page itself (via PyMuPDF) so the signature
    matches VLMPerceptionProvider.perceive exactly -- callers never need
    to know this provider needs an image."""

    def __init__(self, generate_fn: GenerateFn, zoom: float = 2.0):
        self._generate_fn = generate_fn
        self._zoom = zoom

    def _render_page(self, pdf_path: str, page_number: int):
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]  # fitz is 0-indexed; ALIM pages are 1-indexed
        mat = fitz.Matrix(self._zoom, self._zoom)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")

    def perceive(self, pdf_path: str, page_number: int, query: str) -> List[Candidate]:
        from alim.integrations.qualcomm.schema import build_prompt
        image_bytes = self._render_page(pdf_path, page_number)
        prompt = build_prompt(query)
        raw_text = self._generate_fn(image_bytes, prompt)
        return parse_evidence_to_candidates(raw_text, default_page=page_number)
