"""
Downloads the real datasheet PDF fixtures used by the regression tests.
These are NOT bundled in this repository -- they are third-party
manufacturer copyrighted documents, fetched here at test-setup time from
the same public source used during development, rather than redistributed.

Run this once before `pytest alim/tests/`.
"""
import os
import urllib.request

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "alim", "tests", "fixtures")
BASE = "https://raw.githubusercontent.com/arduinolearning/Datasheets/master/"
FILES = ["DS18b20.pdf", "LM35.pdf", "MQ-7.pdf", "nRF24L01P.PDF", "MLX90614.pdf"]

if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    for f in FILES:
        path = os.path.join(FIXTURES_DIR, f)
        if os.path.exists(path):
            print(f"already present: {f}")
            continue
        urllib.request.urlretrieve(BASE + f, path)
        print(f"fetched: {f} ({os.path.getsize(path)} bytes)")
