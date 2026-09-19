"""
Minimal usage example. Run `python fetch_fixtures.py` first.
"""
import json
from alim.api.extract import extract

result = extract(
    pdf_path="alim/tests/fixtures/nRF24L01P.PDF",
    query="operating supply voltage",
)
print(json.dumps(result, indent=2))
