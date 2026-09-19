# VERIFICATION_REPORT.md

Scope: everything actually run and checked against this codebase, across all development
sessions. Every number below was reproduced immediately before writing this report (see
"Reproduction" at the bottom). Nothing here is projected or extrapolated from a smaller sample.

## Environment

- Python 3.12.3, pdfplumber 0.11.9, pytest 9.1.1
- No GPU, no network access to any model endpoint (relevant to the "no live VLM" limitation)
- Package installed editable (`pip install -e .`); tests run via plain `pytest` from repo root
  (pyproject.toml sets `pythonpath = ["."]` and `testpaths = ["alim/tests"]`)

## 1. Regression test inventory (15/15 passing)

### `alim/tests/test_decision_scenarios.py` — decision core in isolation (hand-built candidates)

| Test | What it checks | Data |
|---|---|---|
| `test_mislabeled_header_full_context_rejects_absolute_max` | Caption-verified negative selection correctly rejects an Absolute-Maximum row | Real nRF24L01+ values |
| `test_mislabeled_header_cropped_call_is_ambiguous_not_confidently_wrong` | With no caption available and identical (one wrong) section text on both sides, returns `AMBIGUOUS` rather than a confident wrong answer | Real nRF24L01+ values |
| `test_duplicated_candidates_collapse_to_one` | Two identical candidates (simulating an overlapping extraction pass) collapse to one, not two "corroborating" votes | Synthetic |
| `test_split_condition_same_table_flags_missing_condition` | Same table, same parameter, blank condition, conflicting values → `AMBIGUOUS_MISSING_CONDITION`, not a silent pick | Real nRF24L01+ values, condition text deliberately blanked to simulate a VLM perception loss |
| `test_decoy_rail_does_not_win` | A plausible but wrong rail (AVDD) does not win over the correct one (VDDIO) for "interface supply voltage" | Real BME280-style values |
| `test_missing_section_field_flags_uncertain` | A candidate with no section field at all does not default to a false PASS | Real LM317 VI-VO collision |
| `test_footnote_is_preserved_not_dropped` | A footnote attached to the winning candidate reaches the final result | Real MLX90614-style PWM section |
| `test_multi_condition_values_all_preserved` | Three genuinely distinct conditions for one parameter are all preserved, not collapsed | Real BME280 oversampling-current values |
| `test_malformed_value_rejected_not_crashed` | An OCR-style misread value (`l.71`) is excluded, not silently coerced | Synthetic (models real OCR failure mode) |
| `test_genuinely_absent_parameter_returns_not_found` | No matching candidate → `NOT_FOUND` | Synthetic |

### `alim/tests/test_structural_failures.py` — structural pipeline against real PDF fixtures

| Test | Failure class | Real fixture |
|---|---|---|
| `test_failure5_schema_misdetection_lm35_device_variant_refused` | Schema misdetection causing silent data loss | LM35.pdf (TI) |
| `test_failure7_merged_header_mlx90614_refused_not_forced` | Structurally mismatched table forced into wrong schema | MLX90614.pdf (Melexis) |
| `test_failure4_section_numbering_not_read_as_data_ds18b20` | Section/table numbering read as engineering data | DS18b20.pdf (Maxim) |
| `test_failure3_multi_condition_rows_not_collapsed_ds18b20` | Multiple condition subrows collapsing into one blob | DS18b20.pdf |
| `test_failure1_and_2_ds18b20_real_rows_have_clean_numeric_fields` | Condition-embedded numbers / 2-number-row ambiguity | DS18b20.pdf |

Run: `pytest -v` → **15 passed**.

## 2. Live bug-discovery log for this verification pass

This is the part of "mature engineering" that matters most: what actually broke when tested,
not just what passed. In chronological order, this session:

1. **`AMBIGUOUS_MISSING_CONDITION` guard mis-gated.** First implementation still let a
   same-table, blank-condition, conflicting-value pair through as confident `FOUND` because
   the guard checked "not all caption-verified" instead of "conditions don't distinguish."
   Fixed; regression test added.
2. **Field-map silent data loss, one layer deeper than previously fixed.** The real nRF24L01+
   Absolute Maximum table (header literally reads "Operating conditions") produced *zero*
   candidates even after the section-classification fix, because no column was recognized as
   "Parameter" either. This meant an earlier "correct" result was still winning by accident
   (the competing table silently contributed nothing) rather than by genuine rejection. Fixed
   with a general leftmost-column fallback; re-verified the rejection is now real (see §3).
3. **`±` tolerance notation rejected as malformed.** DS18B20's real Thermometer Error row
   (`±½°C`, `±2°C`) failed value-quality checks and caused a real, existing parameter to
   return `NOT_FOUND`. Fixed by extending the numeric-value recognizer.
4. **`unresolved_tables` noise.** A successful extraction on a 78-page real document buried
   the answer under ~150 mostly-irrelevant flagged tables. Fixed: count-only by default.
5. **Symbol-vs-text grouping.** A real table with only a combined "Parameter (condition)"
   column produced different `detected_parameter` text for two rows of the *same* real
   parameter, which would have silently broken multi-condition grouping for that table shape.
   Fixed by grouping on symbol when available.
6. **That fix immediately regressed test #2 above** by conflating "same table" ambiguity with
   "different tables, same symbol" ambiguity. Caught by the existing regression suite within
   the same session, not discovered later. Fixed by requiring page-agreement before treating a
   symbol match as "same table."

Every one of these was found by either the regression suite or an end-to-end run against real
PDFs, not asserted from design review. Two (#2, #6) were only discoverable because the
previous session's tests still existed and were re-run after each change, per the "run the
full suite before declaring anything fixed" rule.

## 3. Re-verification of the marquee real case (nRF24L01+ Absolute Max vs Operating)

Before this session, the "correct" `VERIFIED` answer for "operating supply voltage" was
produced by an *accident* (the competing Absolute-Maximum table generated zero candidates due
to bug #2 above, not because it was genuinely rejected). Re-checked after the fix:

```
status: FOUND
  rejected: VDD -0.3 3.6 -> structural (VERIFIED): negative-selection rejection
  accepted: Supply voltage 1.9 3.6
```

The rejection is now real: the Absolute-Maximum row is present as a candidate and explicitly
rejected via the negative-selection mechanism, not absent. This is the single most important
verification result in this report -- the previous "success" was not actually validating what
it appeared to validate.

## 4. End-to-end results (`examples/e2e_smoke_test.py`, real PDFs, full pipeline)

| Datasheet | Query | Result | Latency |
|---|---|---|---|
| DS18b20.pdf | supply voltage | FOUND (3.0\u20135.5V) | 1.47s |
| DS18b20.pdf | thermometer error | FOUND (2 conditions preserved) | 1.56s |
| LM35.pdf | supply voltage | SCHEMA_UNKNOWN (device-variant table, correctly refused) | 0.66s |
| MLX90614.pdf | external supply | SCHEMA_UNKNOWN (merged-header table, correctly refused) | 7.31s |
| nRF24L01P.PDF | operating supply voltage | VERIFIED (1.9\u20133.6V) | 7.17s |
| nRF24L01P.PDF | storage temperature | VERIFIED (-40 to +125\u00b0C, restricted-query path) | 7.05s |
| MQ-7.pdf | supply voltage | SCHEMA_UNKNOWN | 0.59s |

MQ-7 was never used to develop any heuristic in this codebase -- included specifically as an
unseen-document sanity check. Correct refusal on unfamiliar layout is the right outcome, not a
failure to extract.

## 5. Benchmark (`alim/benchmarks/run_benchmark.py`)

| File | Pages | Tables found | Ingestion time | ms/page |
|---|---|---|---|---|
| DS18b20.pdf | 26 | 25 | 1.44s | 55 |
| LM35.pdf | 13 | 2 | 0.66s | 51 |
| MQ-7.pdf | 3 | 11 | 0.63s | 211 |
| nRF24L01P.PDF | 78 | 179 | 6.84s | 88 |
| MLX90614.pdf | 51 | 50 | 7.55s | 148 |

Total corpus ingestion: ~17s for 5 files. No caching across repeated queries against the same
document exists yet -- each `extract()` call re-ingests the whole PDF (confirmed: two queries
against nRF24L01P.PDF cost ~7s each, ~14s combined, for content that only needed parsing once).

## 6. What this report does not cover

No labeled ground-truth precision/recall numbers (would need a larger, manually-labeled
corpus). No RAM/CPU profiling (wall-clock was the informative number with no VLM calls yet to
dominate cost). No adversarial fuzzing beyond the fixture set. Full itemized gap list against
the original 26-section spec is in `LIMITATIONS.md`.

## 7. Reproduction

```
pip install -r requirements.txt
pip install -e .
python fetch_fixtures.py
pytest -v
python examples/e2e_smoke_test.py
python alim/benchmarks/run_benchmark.py
```

## 8. Sign-off

15/15 regression tests passing, including 5 tests against real PDF fixtures. Six real defects
were found and fixed during this specific verification pass (not carried over from
unverified prior claims), each with an immediate re-run of the full suite. Classification
remains **research prototype with a validated decision core** -- this report increases
confidence in that core, it does not change the classification, because the corpus size (5
documents), missing VLM integration, and 8 unhandled schema shapes are unchanged.
