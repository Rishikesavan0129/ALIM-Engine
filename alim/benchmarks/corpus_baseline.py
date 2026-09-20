"""
Structural-only baseline (no VLM) across the full real-datasheet fixture
corpus. Run this BEFORE a VLM batch test: it tells you which documents
already resolve without a VLM at all, versus which ones genuinely need
one -- so a VLM evaluation isn't wasted re-testing documents that don't
exercise the VLM path.

One representative query per document, chosen by category (not
exhaustive -- this is a baseline, not the adversarial suite). Run with:
    python alim/benchmarks/corpus_baseline.py
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from alim.api.extract import extract
from fetch_fixtures import CATEGORY

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")

QUERIES = {
    "DS18b20.pdf": "supply voltage",
    "LM35.pdf": "supply voltage",
    "MQ-7.pdf": "supply voltage",
    "nRF24L01P.PDF": "operating supply voltage",
    "MLX90614.pdf": "external supply",
    "LM317.pdf": "operating input to output differential voltage",
    "LM7805.pdf": "input voltage",
    "LM358.pdf": "supply voltage",
    "LM741.pdf": "supply voltage",
    "TL082.pdf": "supply voltage",
    "LM339.pdf": "supply voltage",
    "NE555.pdf": "supply voltage",
    "CA3306.pdf": "supply voltage",
    "MCP4725.pdf": "supply voltage",
    "CD4017.pdf": "supply voltage",
    "KA34063.pdf": "supply voltage",
    "BMP180.pdf": "supply voltage",
    "VL53L0X.pdf": "supply voltage",
    "STM32F103C8.pdf": "supply voltage",
    "AT24C02A.pdf": "supply voltage",
    "AT45DB041B.pdf": "supply voltage",
    "74HC595.pdf": "supply voltage",
}

if __name__ == "__main__":
    results = []
    for fname, query in QUERIES.items():
        path = os.path.join(FIXTURES, fname)
        if not os.path.exists(path):
            print(f"SKIP {fname}: not found -- run fetch_fixtures.py first")
            continue
        t0 = time.time()
        try:
            r = extract(path, query)
            status = r["status"]
        except Exception as e:
            status = f"ERROR: {type(e).__name__}: {e}"
        dt = time.time() - t0
        results.append((fname, CATEGORY.get(fname, "?"), query, status, dt))

    print(f"{'file':18s} {'category':18s} {'query':45s} {'status':14s} {'time':>6s}")
    print("-" * 105)
    for fname, cat, query, status, dt in results:
        print(f"{fname:18s} {cat:18s} {query:45s} {status:14s} {dt:5.2f}s")

    counts = {}
    for *_rest, status, _dt in results:
        counts[status] = counts.get(status, 0) + 1
    print("\n--- summary ---")
    for status, n in sorted(counts.items()):
        print(f"{status:14s}: {n}")
    print(f"total documents: {len(results)}")
    print(f"total time: {sum(r[4] for r in results):.1f}s")
