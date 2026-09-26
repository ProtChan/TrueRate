from datetime import date
import unittest

from truerate.margins import OTC_PAIR_MARGIN_RATES, parse_click365_margin_csv


CSV_TEXT = """20260928,20261002
USD/JPY,62280
ZAR/JPY,38260
HUF/JPY,19700
EUR/USD,71650
USL/JPY,622790
"""


class MarginParserTest(unittest.TestCase):
    def test_click365_contract_amounts_are_normalized_to_10k_base(self):
        data = parse_click365_margin_csv(
            CSV_TEXT,
            source_url="https://example.invalid/margin.csv",
        )
        self.assertEqual(data["effective_start"], "2026-09-28")
        self.assertEqual(data["effective_end"], "2026-10-02")
        self.assertEqual(data["per_pair_jpy"]["USD/JPY"], 62280.0)
        self.assertEqual(data["per_pair_jpy"]["EUR/USD"], 71650.0)
        self.assertEqual(data["per_pair_jpy"]["ZAR/JPY"], 3826.0)
        self.assertEqual(data["per_pair_jpy"]["HUF/JPY"], 1970.0)
        self.assertNotIn("USL/JPY", data["per_pair_jpy"])

    def test_current_otc_pair_margin_exceptions(self):
        self.assertEqual(OTC_PAIR_MARGIN_RATES["sbi_fx"]["BRL/JPY"], 0.10)
        self.assertEqual(OTC_PAIR_MARGIN_RATES["sbi_fx"]["RUB/JPY"], 0.33)
        self.assertEqual(OTC_PAIR_MARGIN_RATES["minfx"]["RUB/JPY"], 0.10)
        self.assertEqual(OTC_PAIR_MARGIN_RATES["lightfx"]["RUB/JPY"], 0.10)


if __name__ == "__main__":
    unittest.main()
