import sys, os, time, json

from alim.api.extract import extract

FIXTURES = "alim/tests/fixtures"

CASES = [
    ("DS18b20.pdf", "supply voltage"),
    ("DS18b20.pdf", "thermometer error"),
    ("LM35.pdf", "supply voltage"),          # expect SCHEMA_UNKNOWN (device-variant table, correctly refused)
    ("MLX90614.pdf", "external supply"),     # merged-header table -> expect SCHEMA_UNKNOWN
    ("nRF24L01P.PDF", "operating supply voltage"),
    ("nRF24L01P.PDF", "storage temperature"),
    ("MQ-7.pdf", "supply voltage"),          # unseen-during-development, honest test of generalization
]

results = []
for fname, query in CASES:
    path = os.path.join(FIXTURES, fname)
    t0 = time.time()
    r = extract(path, query, trace=False)
    dt = time.time() - t0
    r["_latency_s"] = round(dt, 3)
    results.append((fname, query, r))
    print(f"\n=== {fname} :: {query!r} ({dt:.2f}s) ===")
    print(json.dumps({k: v for k, v in r.items() if k != "_latency_s"}, indent=2)[:800])

print("\n\n--- SUMMARY ---")
for fname, query, r in results:
    print(f"{fname:16s} {query:32s} -> {r['status']:28s} ({r['_latency_s']}s)")
