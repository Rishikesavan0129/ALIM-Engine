import sys, os, time, statistics

from alim.ingestion.pdf_extract import extract_document
from alim.api.extract import extract

FIXTURES = "alim/tests/fixtures"
FILES = ["DS18b20.pdf", "LM35.pdf", "MQ-7.pdf", "nRF24L01P.PDF", "MLX90614.pdf"]

print("--- ingestion-only latency (no caching across calls -- known perf gap) ---")
ingest_times = {}
for f in FILES:
    path = os.path.join(FIXTURES, f)
    t0 = time.time()
    doc = extract_document(path)
    dt = time.time() - t0
    ingest_times[f] = dt
    n_tables = sum(len(p.tables) for p in doc.pages)
    n_pages = len(doc.pages)
    print(f"{f:16s} {n_pages:3d} pages  {n_tables:3d} tables  {dt:6.2f}s  ({dt/n_pages*1000:.0f} ms/page)")

print(f"\nmean ingestion latency: {statistics.mean(ingest_times.values()):.2f}s")
print(f"total for this 5-file corpus: {sum(ingest_times.values()):.2f}s")

print("\n--- full extract() latency, single query each (includes re-ingestion every call) ---")
queries = [("DS18b20.pdf", "supply voltage"), ("nRF24L01P.PDF", "operating supply voltage"),
           ("MLX90614.pdf", "external supply")]
for fname, q in queries:
    t0 = time.time()
    r = extract(os.path.join(FIXTURES, fname), q)
    dt = time.time() - t0
    print(f"{fname:16s} {q:30s} {dt:6.2f}s  -> {r['status']}")
