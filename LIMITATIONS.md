# LIMITATIONS.md — itemized against the original task spec

This maps each numbered section of the production task to what actually happened, honestly.

**§5 IR.** Bounding boxes, page numbers, table boundaries, cell contents, and caption/heading
text are preserved. Font information, true multi-column reading order, and merged-cell spans
as first-class structure are NOT preserved -- a merged header still arrives as a grid row with
phantom empty cells (handled by refusing the table, not by reconstructing the true span).
Formula-valued bounds (`VDD - 0.3`) are recognized by `FORMULA_RE` as "not malformed" but are
NOT decomposed into the `{value, relation, reference, bound}` structure the spec describes --
they pass through as an opaque string. This is a real, named gap, not a silent one: a query
whose answer is a formula-valued bound will return that string as-is.

**§6 Schema classification.** 6 of 14 listed shapes handled (see README). Narrative
(non-tabular) specifications are not extracted at all -- `pdfplumber.find_tables()` finds
nothing for prose, so that content is invisible to this pipeline, not refused-with-a-reason.
Cross-page continuation tables are not detected as continuations of each other; each table
object is independent per page.

**§7 Seven structural failure classes.** All 7 have a corresponding regression test against
real PDF fixtures (`tests/test_structural_failures.py`). Failures 1-3 (condition-embedded
numbers, 2-number-row ambiguity, multi-row collapse) are substantially improved by real
column-position-based extraction plus the multiline-zip rule, verified on real data, not
claimed from theory. Failure 6 (formula-valued bounds) is NOT fixed -- see IR note above.
Failures 4, 5, 7 have working regression tests and pass on the current fixture set.

**§8-9 VLM integration and evidence scope.** No live model wired (see README). The
`ManualVLMProvider` stand-in and the confidence-tier distinction between full-page and
cropped-region evidence are implemented and unit-tested, but this is a documented contract
plus test fixtures, not a working multimodal pipeline. Do not represent this as "VLM
integrated" in any pitch context without this caveat attached.

**§10 Confidence model.** 4 of 6 named levels are actually produced (`VERIFIED`,
`STRONGLY_SUPPORTED`, `UNVERIFIED`, `NONE`). `SUPPORTED` and `AMBIGUOUS` exist in the enum,
unused. Do not claim 6-level confidence is implemented; claim 4, honestly.

**§14 Real-datasheet validation.** 5 datasheets, 5 manufacturers, sensors + regulator +
op-amp + transceiver represented; ADC, MCU, memory, logic, and power-management device
classes from the requested list are NOT represented in this corpus. MQ-7 was used as an
unseen-during-heuristic-development sanity check (result: correctly refused as
`SCHEMA_UNKNOWN`, its tables are a `Technical condition`/`Remark`-style layout our classifier
correctly doesn't recognize -- refusal, not silent wrong data, which is the right failure mode
even though it means zero extraction from that file today).

**§15 Adversarial test suite.** A meaningful subset is covered (identical parameter names
across sections, Operating vs Absolute Maximum, multi-rail ambiguity, 2-number rows,
multi-row conditions, formulas-as-opaque-strings, merged cells, section/table numbering,
variant columns, register bitfields, misleading headers, missing conditions, conflicting
values). NOT covered: OCR noise, scanned/image-only pages, units-only-in-footnotes,
units-only-in-headers as a distinct extraction path, cross-page continuation.

**§16 Evaluation metrics.** Only latency was actually measured (see benchmark output in the
final response). Parameter precision/recall, exact-value accuracy, false-positive rate, and
per-vendor/per-table-type breakdowns are NOT computed -- they require a labeled ground-truth
set larger than 5 documents to mean anything, and building that labeled set was out of scope
for this session.

**§17 Performance.** No caching across calls (named in README). No page-render resolution
control because no VLM path exists yet to need one. Ingestion averaged ~50-200ms/page across
the 5 fixtures on CPU; total corpus ingestion (5 files) was ~17s, dominated by the two larger
documents (51 and 78 pages).

**§18 Determinism.** Code contains no randomness. No explicit seed/tie-break management was
added because none was needed to reproduce any result in this session -- this has not been
stress-tested under concurrent or reordered input.

**§19 Failure handling.** Implemented: `SCHEMA_UNKNOWN`, `NOT_FOUND`, `AMBIGUOUS`,
`AMBIGUOUS_MISSING_CONDITION`, `VLM_REQUIRED` (raised by `NoVLMConfigured`, not yet
surfaced as a top-level API status string -- currently only reachable by calling a
`VLMPerceptionProvider` directly). NOT implemented as distinct states:
`TABLE_NOT_RECONSTRUCTABLE`, `INSUFFICIENT_CONTEXT`, `AMBIGUOUS_PARAMETER` (currently folded
into `AMBIGUOUS`), `CONFLICTING_CANDIDATES` (folded into `AMBIGUOUS_MISSING_CONDITION`),
`FORMULA_UNRESOLVED`, `EXTRACTION_FAILED`.

**§20 Overfitting.** Every heuristic added this session is justified in the README CHANGELOG
with either a cross-manufacturer confirmation or a stated general document-structure
rationale. No hardcoded page numbers or parameter locations exist in production code (test
files do reference specific real page numbers, which is appropriate for regression tests, not
production logic).

**What was explicitly NOT attempted this session, and why:** a live VLM call path (no network
route available), a 15-20 document labeled corpus with precision/recall metrics (requires
ground-truth labeling effort beyond one session), the remaining 8 schema shapes (each would
need its own real-example-driven design, not a guess), RAM/CPU profiling beyond wall-clock
timing (not requested as urgently as correctness, and wall-clock was the more informative
number given no VLM calls exist yet to dominate cost).
