# Qualcomm AI LAB Build & Present Challenge — ALIM Integration

This document is the record of the actual research and decisions behind the Qualcomm
integration, not a marketing summary. Every claim below is either a citation to something
checked live during this work (Qualcomm AI Hub pages, fetched on the date this was written) or
is explicitly marked as unverified.

## 1. Model selection

**Selected: `Qwen3-VL-4B-Instruct`**, not the originally-suggested `Qwen2.5-VL-7B-Instruct`.

Checked directly against the current Qualcomm AI Hub compute catalog (`aihub.qualcomm.com/compute/models`):

| | Qwen2.5-VL-7B-Instruct | Qwen3-VL-4B-Instruct |
|---|---|---|
| Parameters | 7B | 4B |
| Generation | Qwen2.5 | Qwen3 (newer) |
| Supported Compute chipsets | Snapdragon X Elite, X Plus 8-Core, X2 Elite | Same three |
| Runtime | GenieX \u2013 QAIRT | Same |
| License | Apache-2.0 | Apache-2.0 |
| Qualcomm's own description | "State-of-the-art vision-language model" | "Enhanced visual reasoning capabilities" |
| Published on-device benchmark numbers | Not found as of this writing | **Found** \u2014 see \u00a73 |

4B vs 7B is the deciding factor for a datasheet-table-reading task specifically: this workload
needs careful structured reading of small, dense text, not broad open-domain visual reasoning,
so the smaller model's latency/memory advantage matters more than raw capacity. Both are
Apache-2.0 and both target the identical chipset list, so there's no compatibility trade-off
either way.

**Fallback options, in order, if 4B proves insufficient in practice:**
- `Qwen3-VL-2B-Instruct` if latency/memory needs to go lower and accuracy loss is acceptable.
- `Qwen2.5-VL-7B-Instruct` if 4B's visual reasoning turns out too weak for small/dense table
  text specifically \u2014 this is a real, plausible failure mode that has not been tested (no
  live model access in the environment that did this research; see \u00a75).

Source: `https://aihub.qualcomm.com/compute/models`, `https://aihub.qualcomm.com/compute/models/qwen3_vl_4b_instruct`, `https://aihub.qualcomm.com/compute/models/qwen2_5_vl_7b_instruct` (fetched live).

## 2. Runtime clarification: GenieX, QAIRT, llama.cpp

"GenieX" is confirmed as a real, current Qualcomm on-device generative-AI SDK/runtime name
(not a typo for "Genie" \u2014 both exist; Qualcomm's own AI Hub docs note "Genie support will be
deprecated soon" in favor of GenieX). AI Hub's runtime filter for this model lists three
variants:

- **GENIE** \u2014 the runtime being deprecated.
- **GENIEX_QAIRT** \u2014 w4a16 quantization, uses the Hexagon NPU via Qualcomm's AI Runtime (QAIRT).
  This is the intended production path for Snapdragon X Elite/Plus/X2. Published performance:
  see \u00a73.
- **GENIEX_LLAMACPP** \u2014 q4_0 GGUF quantization, runs via llama.cpp. Notably, the exact GGUF file
  Qualcomm ships for this path (`unsloth/Qwen3-VL-4B-Instruct-GGUF`, Q4_0) can also run via
  llama.cpp on a normal x86 machine (including inside Colab) \u2014 same weights, same
  quantization, different (non-NPU) execution path. This is the closest thing to a portable,
  Colab-runnable proxy for the actual on-device quantization, though it still isn't genuine
  Snapdragon/NPU execution. Not used in the current notebook (transformers/GPU was chosen
  instead, for simpler setup); worth trying if llama.cpp's vision support for Qwen3-VL is
  confirmed mature at the time you read this \u2014 not verified here.

Source: `https://aihub.qualcomm.com/geniex`, model page runtime filters and quick-start commands (fetched live).

## 3. Real, published on-device benchmark numbers (not measured by this project)

Qualcomm publishes real Snapdragon X Elite performance numbers for this exact model on its
Hugging Face model card. These are **cited, not reproduced** \u2014 this project did not run them:

| Runtime | Precision | Chipset | Context | Response Rate (tok/s) | TTFT range (s) |
|---|---|---|---|---|---|
| GENIEX_QAIRT | w4a16 | Snapdragon X Elite | 4096 | 20.89 | 0.1 \u2013 3.2 |
| GENIEX_QAIRT | w4a16 | Snapdragon X2 Elite | 4096 | 39.22 | 0.047 \u2013 1.50 |
| GENIEX_LLAMACPP | q4_0 | Snapdragon X Elite | 512 | 21.9 / 22.1 / 11.5 (3 runs) | 0.375 \u2013 2.08 |
| GENIEX_LLAMACPP | q4_0 | Snapdragon X Elite | 4096 | 7.6 / 8.5 / 7.6 (3 runs) | 0.58 \u2013 43.3 |

Source: `https://huggingface.co/qualcomm/Qwen3-VL-4B-Instruct` (Performance Summary table,
fetched live). These are text-generation throughput/TTFT numbers for the model generally, not
specific to the datasheet-extraction prompt used in this project \u2014 a longer structured-JSON
prompt with an image will behave differently, especially TTFT (image tokens add to prompt
processing time). No number in this row was adjusted, extrapolated, or re-measured.

## 4. Colab vs on-device: what the notebook actually validates

Google Colab VMs are x86 Linux cloud machines with no Snapdragon silicon, no Hexagon NPU, and
no GenieX/QAIRT runtime. **The notebook cannot execute genuine on-device inference.** It
validates two things:
1. The evidence schema and prompt design produce parseable, correctly-structured output from
   a real current-generation VLM (Colab GPU inference via Hugging Face `transformers`, loading
   the original `Qwen/Qwen3-VL-4B-Instruct` checkpoint \u2014 the `qualcomm/` HF repo only hosts
   pre-exported on-device runtime assets, not a `transformers`-loadable checkpoint).
2. The existing, unmodified ALIM decision core correctly resolves real adversarial cases
   (the nRF24L01+ mislabeled-header table) using that real model's output.

It does not validate on-device latency, memory, or NPU utilization. Genuine device evidence
requires either a physical Snapdragon-on-Windows machine running GenieX, or Qualcomm AI Hub
Workbench's hosted device farm (`qai-hub` Python SDK, callable from Colab, requires your own
Qualcomm AI Hub account/API token \u2014 see the notebook's \u00a78, not run in this project).

## 5. What was NOT verified, and why

- **No live model call was made anywhere in this project.** The sandbox that did this research
  and wrote this integration has no network route to `huggingface.co` or any model-serving
  endpoint (only package registries are reachable). All integration-layer tests
  (`alim/tests/test_qualcomm_integration.py`) use a fixture `generate_fn` returning hand-written
  JSON representing plausible model output \u2014 they prove the parsing/decision integration is
  correct, not that a real Qwen3-VL-4B-Instruct call would produce JSON in that exact shape.
  **The first real-model run happens when you run the notebook.**
- **No AI Hub Workbench profiling was run.** Requires an account/token this project doesn't have.
- **No accuracy comparison between Qwen3-VL-4B and Qwen2.5-VL-7B on datasheet tables specifically
  exists.** The model-selection argument in \u00a71 is architectural/resource reasoning, not a
  measured accuracy result.
- **The `exec` output shape in transformers' chat-template / generation API for Qwen3-VL was
  written from the standard current Qwen-VL pattern, not confirmed against a live install.** If
  `AutoModelForImageTextToText` doesn't recognize this architecture in your installed
  `transformers` version, upgrade or check the model card for the current class name.

## 6. Real-datasheet corpus: 22 documents, structural-only baseline

Extended the fixture corpus from 5 to **22 real datasheets** across the device categories the
challenge spec named: sensors (DS18B20, LM35, MQ-7, MLX90614, BMP180, VL53L0X), an RF
transceiver (nRF24L01+), regulators (LM317, LM7805), op-amps (LM358, LM741, TL082), a
comparator (LM339), a timer (NE555), an ADC (CA3306), a DAC (MCP4725), logic ICs (74HC595,
CD4017), an MCU (STM32F103C8), memory (AT24C02A, AT45DB041B), and a power-management IC
(KA34063). Source: two public GitHub-hosted collections (`arduinolearning/Datasheets`,
`Vitorbnc/electronics-datasheets`), fetched at test-setup time via `fetch_fixtures.py`, never
committed as binaries. One deliberate omission: the full ATmega48/88/168/328 family datasheet
(32MB, 600+ pages) was dropped as disproportionate for a test fixture.

**Structural-only baseline** (`alim/benchmarks/corpus_baseline.py`, no VLM, one representative
query per document, run and recorded on this date):

| Status | Count |
|---|---|
| VERIFIED | 1 |
| FOUND | 3 |
| AMBIGUOUS_MISSING_CONDITION | 1 |
| NOT_FOUND | 7 |
| SCHEMA_UNKNOWN | 10 |

Read plainly: only 4 of 22 real documents resolve with a confident answer from structure
alone. 10 come back `SCHEMA_UNKNOWN` -- a table-shaped grid was found but its schema wasn't
recognized (device-variant columns, merged headers, or shapes the classifier hasn't seen) --
**these are exactly the documents where the VLM fallback is supposed to help**, and the
notebook's \u00a710 batch cell runs the identical query set through a configured VLM provider so
you can measure how many of those 10 actually resolve. 7 come back `NOT_FOUND`, which is not
automatically a VLM problem -- structural candidates may well exist on these pages but not
match the exact query wording used (e.g. a chip's supply pin might only be labeled "VCC" with
no "voltage" token nearby); this needs per-document investigation, not assumed to be either a
parsing failure or a vocabulary success. The one `AMBIGUOUS_MISSING_CONDITION` (LM7805) is a
genuinely interesting real find: multiple input-voltage values with no distinguishing
condition text -- worth checking by hand against the real datasheet before assuming it's a bug
or a real ambiguity in the source document.

**This baseline was measured, not estimated** -- every row is a real `extract()` call against
a real PDF in this session. It has not yet been run with a real VLM anywhere; that's what the
notebook's \u00a710 cell is for.

## 7. Reproduction

```bash
# Integration-layer tests (fixture backend, no live model, works anywhere):
pip install -r requirements.txt && pip install -e .
python fetch_fixtures.py
pytest alim/tests/test_qualcomm_integration.py alim/tests/test_vlm_fallback_orchestration.py -v

# Full notebook (real model, requires Colab or a local GPU machine):
# open examples/qualcomm_alim_colab.ipynb, set ALIM_REPO_URL, set MOCK_MODE = False
```
