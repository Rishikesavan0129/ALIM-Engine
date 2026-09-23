"""
The evidence contract this integration asks a VLM to fill in, and the
prompt that asks for it. Kept deliberately separate from any specific
model backend (Hugging Face transformers, GenieX CLI, AI Hub Workbench) --
see provider.py for the backend-specific pieces.

Design rule from the task spec, enforced here structurally: the VLM
supplies evidence fields. It is never asked to output a single "answer,"
a confidence score it invented, or a decision between competing
candidates -- ALIM's decision core does that. The prompt explicitly
instructs the model to emit multiple candidate objects when multiple
rows are visible, and to leave a field blank/null rather than guess.
"""

EVIDENCE_SCHEMA_DESCRIPTION = """\
Return a JSON array. Each element is one candidate parameter reading you can
actually see in the image, with this shape:

{
  "section": string or null,       // the section heading OR caption text, if visible
  "table_caption": string or null, // e.g. "Table 2. Absolute maximum ratings" -- prefer this over a table's own header row if they conflict
  "parameter": string,             // the parameter's label text, as printed
  "symbol": string or null,        // the symbol/reference designator, e.g. "VDD"
  "condition": string or null,     // the condition text for this row, if any
  "min": string or null,
  "typ": string or null,
  "max": string or null,
  "unit": string or null,
  "footnote_text": string or null, // full text of any footnote this value references
  "page": integer,
  "uncertain": boolean             // true if the text is unclear, cut off, or you are guessing at any field
}

Rules:
- If you see multiple rows for different conditions of the same parameter, return
  one candidate per row. Do not merge them or pick one.
- If a table's own header text and its caption or section heading disagree about
  what the table is (e.g. a header says "Operating conditions" but the caption
  says "Absolute maximum ratings"), report BOTH the "section" (from the caption/
  heading) and note the disagreement is real -- do not silently resolve it.
- If a field is not visible or not printed, use null. Never invent a value.
- If a bound is expressed relative to another signal (e.g. "VDD - 0.3"), copy
  that text into min/max as printed -- do not compute a number.
- If a value is printed as a plain two-sided range in one place (e.g.
  "-0.5V to +18V", "-0.5 VDC to +18 VDC"), split it: the first number goes in
  "min", the second in "max". Example: "-0.5 VDC to +18 VDC" becomes
  min="-0.5", max="18", unit="VDC". Do this even if the min and max are not
  in separate table columns -- a single printed range is still two values.
- Only leave min/max/typ null when NO number for that field is printed
  anywhere for this row, not when it needs to be split out of a range.
- Return [] if no relevant parameter is visible on this page.
- Do not decide which candidate is "correct" -- that is not your job.
"""


def build_prompt(query: str) -> str:
    return (
        f"You are extracting structured evidence from a datasheet page image "
        f"for the parameter: \"{query}\".\n\n"
        f"{EVIDENCE_SCHEMA_DESCRIPTION}\n"
        f"Respond with ONLY the JSON array, no other text."
    )
