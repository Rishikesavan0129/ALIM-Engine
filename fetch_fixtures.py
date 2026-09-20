"""
Downloads the real datasheet PDF fixtures used by the regression tests.
These are NOT bundled in this repository -- they are third-party
manufacturer copyrighted documents, fetched here at test-setup time from
public GitHub-hosted collections, rather than redistributed.

22 real datasheets across the device categories the Qualcomm challenge
spec asked for: sensors, regulators, op-amps, comparators, timers,
ADC/DAC, logic ICs, MCUs, memory, power-management, RF transceivers.
One deliberate omission: the full ATmega48/88/168/328 family datasheet
(32MB, 600+ pages) was not included -- disproportionate for a test
fixture; STM32F103C8.pdf covers the MCU category at a practical size.

Run this once before `pytest alim/tests/`.
"""
import os
import urllib.request
import urllib.parse

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "alim", "tests", "fixtures")

# (output filename, repo, path-within-repo) -- two source repos used;
# credited here rather than in every individual file.
SOURCES = [
    ("DS18b20.pdf", "arduinolearning/Datasheets", "DS18b20.pdf"),
    ("LM35.pdf", "arduinolearning/Datasheets", "LM35.pdf"),
    ("MQ-7.pdf", "arduinolearning/Datasheets", "MQ-7.pdf"),
    ("nRF24L01P.PDF", "arduinolearning/Datasheets", "nRF24L01P.PDF"),
    ("MLX90614.pdf", "arduinolearning/Datasheets", "MLX90614.pdf"),
    ("AT24C02A.pdf", "arduinolearning/Datasheets", "AT24C02A.pdf"),
    ("74HC595.pdf", "arduinolearning/Datasheets", "74hc595.pdf"),
    ("LM317.pdf", "Vitorbnc/electronics-datasheets", "ICs/LM317 datasheet 2011.pdf"),
    ("LM7805.pdf", "Vitorbnc/electronics-datasheets", "ICs/LM78XX.pdf"),
    ("LM358.pdf", "Vitorbnc/electronics-datasheets", "ICs/LM358 texas instruments.pdf"),
    ("LM741.pdf", "Vitorbnc/electronics-datasheets", "ICs/LM741.pdf"),
    ("TL082.pdf", "Vitorbnc/electronics-datasheets", "ICs/tl082 - tl084.pdf"),
    ("LM339.pdf", "Vitorbnc/electronics-datasheets", "ICs/LM339.pdf"),
    ("NE555.pdf", "Vitorbnc/electronics-datasheets", "ICs/NE555N.pdf"),
    ("CA3306.pdf", "Vitorbnc/electronics-datasheets", "ICs/CA3306.pdf"),
    ("MCP4725.pdf", "Vitorbnc/electronics-datasheets", "ICs/MCP4725 dac i2c.pdf"),
    ("CD4017.pdf", "Vitorbnc/electronics-datasheets", "ICs/CD4017.pdf"),
    ("KA34063.pdf", "Vitorbnc/electronics-datasheets", "ICs/KA34063.pdf"),
    ("BMP180.pdf", "Vitorbnc/electronics-datasheets", "Sensors/BST-BMP180-DS000-09.pdf"),
    ("VL53L0X.pdf", "Vitorbnc/electronics-datasheets", "Sensors/vl53l0x datasheet.pdf"),
    ("STM32F103C8.pdf", "Vitorbnc/electronics-datasheets", "MCUs/STM32F103C8.pdf"),
    ("AT45DB041B.pdf", "Vitorbnc/electronics-datasheets", "ICs/AT45DB041B 4-megabit flash memory.pdf"),
]

# Category map, for the batch-evaluation report -- not used for fetching.
CATEGORY = {
    "DS18b20.pdf": "sensor", "LM35.pdf": "sensor", "MQ-7.pdf": "sensor",
    "MLX90614.pdf": "sensor", "BMP180.pdf": "sensor", "VL53L0X.pdf": "sensor",
    "nRF24L01P.PDF": "rf_transceiver",
    "LM317.pdf": "regulator", "LM7805.pdf": "regulator",
    "LM358.pdf": "op_amp", "LM741.pdf": "op_amp", "TL082.pdf": "op_amp",
    "LM339.pdf": "comparator", "NE555.pdf": "timer",
    "CA3306.pdf": "adc", "MCP4725.pdf": "dac",
    "74HC595.pdf": "logic", "CD4017.pdf": "logic",
    "STM32F103C8.pdf": "mcu",
    "AT24C02A.pdf": "memory", "AT45DB041B.pdf": "memory",
    "KA34063.pdf": "power_management",
}


def _url(repo, path):
    return f"https://raw.githubusercontent.com/{repo}/master/{urllib.parse.quote(path)}"


if __name__ == "__main__":
    os.makedirs(FIXTURES_DIR, exist_ok=True)
    for fname, repo, path in SOURCES:
        out_path = os.path.join(FIXTURES_DIR, fname)
        if os.path.exists(out_path):
            print(f"already present: {fname}")
            continue
        req = urllib.request.Request(_url(repo, path), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 1000 or data[:4] != b"%PDF":
            print(f"WARNING: {fname} did not look like a valid PDF, skipping")
            continue
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"fetched: {fname} ({len(data)} bytes)")
