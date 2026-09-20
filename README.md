# ALIM — Deterministic Datasheet Parameter Extraction Engine

## Classification: **research prototype with a validated decision core and a working structural pipeline for supported table shapes.** Not a beta engine, not production-ready. See "Honest classification" at the bottom — this is not a hedge, it's a measured conclusion from what's below.

## Architecture (as built, not as aspired to)

```
PDF
 -> ingestion/pdf_extract.py    (pdfplumber bbox-based table grid extraction -> DocumentIR)
 -> schema/classify.py          (table SHAPE classification + section IDENTITY classification,
                                  the latter with an explicit confidence tier)
 -> candidates/build.py         (IR Table -> Candidate list: forward-fill, subscript-join,
                                  multiline-cell zipping, leftmost-column parameter fallback)
 -> vlm/interface.py            (VLMPerceptionProvider contract; a real implementation lives in
                                  integrations/qualcomm/, no live model wired in this environment)
 -> decision/core.py            (the frozen-then-extended decision core: tri-state negative
                                  selection with confidence tiers, dedup, malformed-value
                                  rejection, AMBIGUOUS_MISSING_CONDITION, explainable trace)
 -> api/extract.py              (top-level extract(pdf_path, query, vlm_provider=None) ->
                                  structured result dict; two-phase orchestration -- decides on
                                  structural evidence first, escalates to a VLM provider only
                                  for pages with an unresolved table schema, and only if the
                                  structural pass didn't already produce a confident answer)
 -> integrations/qualcomm/      (QualcommVLMProvider: evidence schema, prompt, JSON-to-Candidate
                                  parser -- see docs/QUALCOMM.md and examples/qualcomm_alim_colab.ipynb)
```

This matches the required principle: **VLM perceives, deterministic engine decides.** The
decision core itself has been changed only when a reproducible test demonstrated a real defect
(see CHANGELOG below) -- never to make a test pass without understanding why it was failing.
The Qualcomm integration adds a real `VLMPerceptionProvider` implementation and wires the
previously-unused `vlm_provider` orchestration path in `api.extract()`, but does not touch
`decision/core.py` at all.

**Repository structure note:** the task spec suggesting this integration proposed a
`src/alim/` layout; this repo keeps the existing `alim/` top-level layout instead, since
renaming it would touch every import and the CI config for no functional benefit, and risk
breaking the 15 previously-passing tests for a cosmetic change. The new pieces
(`alim/integrations/qualcomm/`, `examples/qualcomm_alim_colab.ipynb`,
`alim/tests/test_qualcomm_integration.py`, `docs/QUALCOMM.md`) follow the spec's intent without
the rename.

## What's actually implemented

- Real bbox-based PDF table extraction (not text flattening), with page number, table
  bounding box, caption, and preceding-heading preserved per table.
- Table shape classification into 4 concrete categories (`spec_table`, `single_value_table`,
  `device_variant_unsupported`, `merged_header_unsupported`, `bitfield_unsupported`) plus a
  catch-all refusal (`unknown_unsupported`). That is 6 of the 14 shapes named in the original
  task spec -- see Limitations for the other 8.
- Section identity classification with a 3-tier confidence model actually in use
  (`VERIFIED` from caption, `STRONGLY_SUPPORTED` from a preceding numbered heading,
  `UNVERIFIED` from the table's own header/section text only) plus `NONE`. `SUPPORTED` and
  `AMBIGUOUS` exist in the enum for spec compatibility but are not currently produced by any
  code path -- named, not faked.
- Forward-fill for continuation rows, subscript-symbol normalization, and a general
  multiline-cell-zipping rule for aligned multi-condition cells -- the last of these was only
  implemented after being independently confirmed on two different real manufacturers'
  datasheets (DS18B20 and LM35), specifically to avoid a one-off, overfit rule.
- A tri-state decision core (`FOUND` / `AMBIGUOUS` / `AMBIGUOUS_MISSING_CONDITION` /
  `NOT_FOUND`) with dedup, malformed-value rejection, footnote-caveat preservation, and a
  per-extraction explainable trace.
- 15 passing regression tests: 10 decision-layer scenarios (isolated from ingestion, per the
  "only change the decision core when a test proves a decision-layer defect" rule) and 5
  structural-failure-class tests against real PDF fixtures.
- A real end-to-end run across 5 real, distinct-manufacturer datasheets producing correct
  `VERIFIED`/`FOUND` results, correct `SCHEMA_UNKNOWN` refusals, and one correct
  `NOT_FOUND` -- see benchmark output.

## CHANGELOG — every decision-core change and why it's general, not a one-off

1. **Confidence tier on structural_check (VERIFIED/STRONGLY_SUPPORTED/UNVERIFIED/NONE).**
   Found via `test_mislabeled_header_cropped_call_is_ambiguous_not_confidently_wrong`: a flat
   PASS/FAIL/UNKNOWN let a table's own (real, published, wrong) header text produce a
   confident but incorrect PASS. General because it encodes a document-structure fact true
   across manufacturers: a caption is more reliable than a table's own header, and a numbered
   section heading is more reliable than an isolated header cell with no other corroboration.

2. **AMBIGUOUS_MISSING_CONDITION guard keyed on `conditions_distinguish`, not
   `all_verified_pass`.** Found via `test_split_condition_same_table_flags_missing_condition`:
   the previous guard let two same-table, same-parameter, conflicting-value candidates through
   as a confident `FOUND` because both were caption-verified -- verification of *which table*
   is correct is a different question from whether *anything* explains *why the values
   differ*. General because it only depends on condition-text presence/absence, not on any
   detail of this specific datasheet.

3. **Leftmost-column parameter fallback in `_build_field_map`.** Found via the end-to-end run
   (not a unit test -- a real gap unit tests didn't cover): a table whose header literally
   doesn't contain the word "Parameter" produced zero candidates, silently, even though it
   passed schema classification as a legitimate spec table. General because "the leftmost
   column is the label column" is close to a universal convention in this document class, not
   specific to the one real datasheet (Nordic nRF24L01+) that exposed it.

4. **`NUM_RE`/`value_quality` accepting `\u00b1` and vulgar-fraction glyphs.** Found via the
   end-to-end run: a real, correct tolerance value (`\u00b1\u00bd`, `\u00b12`) was rejected as
   malformed. General because +/- tolerance notation is standard datasheet convention, not
   specific to DS18B20.

5. **Multiline-cell zipping in `candidates/build.py`.** Implemented only after being seen
   independently on two different manufacturers (DS18B20's "Input Logic High" dual-condition
   row, LM35's per-line-aligned condition/value cells) -- the bar set in the task spec for
   adding a general rule rather than a one-off hack.

6. **Symbol-based grouping (`_group_key`) instead of raw parameter-text grouping, with a
   same-page guard.** Found via the end-to-end run against the real nRF24L01+ "Parameter
   (condition)"-only table: two rows for the same real parameter (VDD) got different
   `detected_parameter` text purely because a qualifier ("if input signals >3.6V") is
   embedded in the one combined column that table has, breaking the multi-condition grouping
   logic for that table shape. Fix: group by symbol when available. This fix regressed one
   existing test immediately (`test_mislabeled_header_cropped_call_is_ambiguous_not_confidently_wrong`)
   by conflating "same table, missing condition" with "different tables, coincidentally same
   symbol" -- both now correctly separated by requiring page agreement for the former. General
   because reference designators are the standard identity signal across this document class,
   not specific to one manufacturer's column layout.

7. **`unresolved_tables` capped/hidden by default (`include_unresolved` flag).** Found via the
   end-to-end run on a 78-page real document: the default successful response was carrying
   ~150 mostly-irrelevant "unsupported table" entries (pin diagrams, revision history, timing
   diagrams that `pdfplumber` also detects as grid-shaped). This violated the spec's own
   requirement that the normal successful case stay simple. Fix: report a count by default,
   full detail only on request or on an actual refusal.

8. **VLM fallback orchestration was never actually wired.** `api.extract()` accepted a
   `vlm_provider` parameter and never called it -- found while preparing the Qualcomm
   integration, which is exactly the code path this parameter exists for. Fixed with a
   two-phase design: decide on structural evidence first; only escalate to the VLM, and only
   for the specific pages with an unresolved table, if the structural pass didn't already
   produce a confident answer. The first version of the fix still called the VLM on a page
   that had already resolved successfully, purely because that same page also contained an
   unrelated misdetected "table" (a figure) -- caught by
   `test_vlm_only_called_for_pages_with_unresolved_tables_not_every_page` and fixed by
   deciding on structural evidence before ever considering escalation. General because it's a
   sequencing rule (decide first, escalate only on genuine insufficiency), not specific to any
   one document.

## Qualcomm AI LAB Build & Present Challenge integration

See `docs/QUALCOMM.md` for the full record: model selection (Qwen3-VL-4B-Instruct, chosen over
the originally-suggested Qwen2.5-VL-7B-Instruct after checking the current AI Hub catalog
directly), the GenieX/QAIRT runtime path, real published on-device Snapdragon X Elite/X2 Elite
benchmark numbers (cited, not reproduced by this project), and the honest Colab-vs-real-device
distinction. Run `examples/qualcomm_alim_colab.ipynb` (works immediately in `MOCK_MODE = True`
with no GPU; set `MOCK_MODE = False` for a real model run on Colab's GPU). Integration tests:
`pytest alim/tests/test_qualcomm_integration.py alim/tests/test_vlm_fallback_orchestration.py -v`.

**Real-datasheet corpus extended to 22 documents** across sensors, an RF transceiver,
regulators, op-amps, a comparator, a timer, an ADC, a DAC, logic ICs, an MCU, memory, and a
power-management IC (`fetch_fixtures.py`). A structural-only baseline (no VLM,
`alim/benchmarks/corpus_baseline.py`) was measured across all 22: only 4 resolve with a
confident structural answer, 10 come back `SCHEMA_UNKNOWN` (the actual target set for VLM
fallback testing), 7 `NOT_FOUND`, 1 `AMBIGUOUS_MISSING_CONDITION`. Full numbers and reading in
`docs/QUALCOMM.md` §6. The notebook's §10 batch cell runs the identical query set through a
configured VLM provider so you can measure how many of the 10 `SCHEMA_UNKNOWN` cases a real
model resolves.

## Honest classification

**Research prototype with a validated decision core and a working structural pipeline for
supported table shapes.**

Why not "beta" or "production-ready":
- The real-datasheet corpus is 5 PDFs across 5 manufacturers, not the 15-20+ across sensors/
  regulators/op-amps/ADCs/MCUs/transceivers/memory/logic/power-management the spec calls for.
  Every number in this repo is honest for n=5, not representative of a larger population.
- No live VLM call has been made anywhere in this project. A real `VLMPerceptionProvider`
  (`QualcommVLMProvider`) and the orchestration to actually invoke it (`api.extract()`'s
  two-phase structural-then-VLM logic) both exist and are tested end-to-end -- but only against
  a fixture backend returning hand-written JSON, since this environment has no network route to
  huggingface.co or any model endpoint. The first genuine model call happens when you run
  `examples/qualcomm_alim_colab.ipynb` with `MOCK_MODE = False`. Until then, any table the
  structural pipeline refuses stays refused when no provider is configured.
- 8 of the 14 named table schemas are not distinguished; they currently fall into the two
  generic refusal buckets rather than being correctly identified and extracted.
- No caching across repeated queries against the same document -- every `extract()` call
  re-parses the whole PDF (see benchmark: this roughly doubles latency for 2 queries against
  one document). Named, not fixed, this session.
- Section-identity classification only recognizes the caption-below and numbered-heading-above
  conventions. A manufacturer using neither gets `NONE` confidence for every row in that
  table, meaning the negative-selection safety net provides no protection there -- this is
  real and currently true for part of DS18B20's own content.
- No determinism guarantees have been added beyond "the code has no randomness in it" --
  there's no seed control, no explicit tie-breaking rule beyond dict/list iteration order, and
  no VLM-output validation layer, because there's no VLM output to validate yet.

See `LIMITATIONS.md` for the full, itemized list against every section of the original task
spec, including what was explicitly out of scope for this session and why.

## License

Apache License 2.0. See `LICENSE`. Copyright 2026 Rishikesavan a.k.a Youness Yunair.
