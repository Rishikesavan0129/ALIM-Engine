"""
Ranks pages by relevance to a query using cheap, deterministic signals
(plain-text keyword/synonym overlap) BEFORE any VLM call. This is the
actual point of running structural extraction first: reduce the search
space with free signals, spend the expensive step only where it's likely
to help.

Found necessary by a real measurement, not by design review: on the real
nRF24L01+ datasheet (78 pages), 77 pages have at least one table-shaped
region the schema classifier doesn't recognize (mostly diagrams and
figures misdetected as tables, not real spec tables). Without this
ranking, escalating to a VLM after a failed structural pass would call it
on 77 pages for one query -- directly against the "minimum VLM
computation necessary" principle stated throughout this project.

Also detects a table-of-contents page when present (common in longer
datasheets) and gives its listed section page numbers a strong boost --
closer to how a person would actually use the document ("find the entry,
jump straight there") than blind per-page keyword scanning.
"""
import re
from alim.decision.core import tokenize, SYMBOL_CONCEPT_TERMS

TOC_ENTRY_RE = re.compile(r'^(.{3,80}?)[\s.\u2026]{3,}(\d{1,4})\s*$')


def _find_toc_page_numbers(doc, query_tokens):
    """Look at the first ~10 pages for a table-of-contents-shaped page
    (many lines of 'Title .... N') and, if found, return page numbers
    whose listed section title overlaps the query."""
    hits = set()
    for page in doc.pages[:10]:
        lines = (page.full_text or "").split("\n")
        toc_lines = [l for l in lines if TOC_ENTRY_RE.match(l.strip())]
        if len(toc_lines) < 3:
            continue  # not a TOC page
        for line in toc_lines:
            m = TOC_ENTRY_RE.match(line.strip())
            if not m:
                continue
            title, page_num = m.group(1), m.group(2)
            title_tokens = tokenize(title)
            if title_tokens & query_tokens:
                hits.add(int(page_num))
    return hits


def rank_pages_by_relevance(doc, query, candidate_pages):
    """Returns candidate_pages sorted by relevance to query, most relevant
    first. Pure text-overlap scoring plus a TOC-derived boost; no VLM
    calls happen here."""
    query_tokens = tokenize(query)
    toc_hits = _find_toc_page_numbers(doc, query_tokens)

    page_text = {p.page_number: (p.full_text or "") for p in doc.pages}
    scored = []
    for page_num in candidate_pages:
        text = page_text.get(page_num, "")
        text_tokens = tokenize(text)
        # expand with the same symbol->concept vocabulary the decision core
        # uses, so a page full of "VDD" scores for a "supply voltage" query
        # even if the word "voltage" never appears on that page.
        expanded = set(text_tokens)
        for tok in text_tokens:
            expanded |= SYMBOL_CONCEPT_TERMS.get(tok, set())
        overlap = len(query_tokens & expanded)
        score = overlap + (10 if page_num in toc_hits else 0)
        scored.append((page_num, score))

    scored.sort(key=lambda x: -x[1])
    return [p for p, _ in scored]
