"""
VLM perception interface.

HONEST LIMITATION: this sandbox has no network path to a multimodal model
endpoint (egress is restricted to package registries), so there is no live
VLM call wired into this pipeline. What exists here is (a) the contract a
real implementation must satisfy, so the decision layer and candidate
schema never need to change when one is wired in, and (b) a
`ManualVLMProvider` that accepts hand-supplied candidate JSON -- which is
exactly how the nRF24L01+ and MLX90614 cases were validated earlier in this
project (a human/model visually read the rendered page and produced
candidate JSON by hand). That is a real, useful stand-in for development
and regression testing. It is not a production VLM integration, and this
module must not be described as one.

The design principle from the spec is preserved: the deterministic layer
never calls a VLM itself. The orchestration layer (api/extract.py) decides
WHEN a VLM is needed (schema refusal, or a page render with no usable
table structure at all) and, if a provider is configured, requests
candidates from it -- which then flow through the exact same
decision.core.extract_parameter as structurally-derived candidates. If no
provider is configured, the orchestration layer returns VLM_REQUIRED
rather than silently producing nothing.
"""
from abc import ABC, abstractmethod
from typing import List

from alim.candidates.build import Candidate


class VLMPerceptionProvider(ABC):
    @abstractmethod
    def perceive(self, pdf_path: str, page_number: int, query: str) -> List[Candidate]:
        """Given a page that the structural pipeline could not confidently
        parse, return whatever candidates a visual read of that page
        supports for this query. Must return Candidate objects with the
        same evidence fields (section, section_confidence, etc.) populated
        as honestly as the perception step can support -- e.g. a provider
        that only sees a cropped table region should NOT populate `section`
        from text it never saw."""
        raise NotImplementedError


class NoVLMConfigured(VLMPerceptionProvider):
    """Default: no VLM available. Callers get an explicit signal to handle,
    not an empty silent result."""
    def perceive(self, pdf_path, page_number, query):
        raise RuntimeError("VLM_REQUIRED: no VLMPerceptionProvider configured")


class ManualVLMProvider(VLMPerceptionProvider):
    """For development/regression testing only. Candidates are supplied by
    the caller ahead of time (keyed by (pdf_path, page_number)), standing in
    for what a real multimodal call would have returned. Used in
    tests/test_vlm_boundary_scenarios.py."""
    def __init__(self):
        self._fixtures = {}

    def register(self, pdf_path: str, page_number: int, candidates: List[Candidate]):
        self._fixtures[(pdf_path, page_number)] = candidates

    def perceive(self, pdf_path, page_number, query):
        return self._fixtures.get((pdf_path, page_number), [])
