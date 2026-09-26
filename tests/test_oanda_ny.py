from datetime import date
import unittest

from truerate.brokers.oanda_ny import parse_month_payload


PAYLOAD = [
    {"date": "09月24日（木）", "sell": "-156.1211", "buy": "88.6077", "days": "1"},
    {"date": "09月25日（金）", "sell": "-155.4506", "buy": "89.0272", "days": "1"},
    {"date": "09月26日（土）", "sell": "", "buy": "", "days": "0"},
]


class OandaNyParserTest(unittest.TestCase):
    def test_yen_amounts_and_business_day_timing(self):
        records = parse_month_payload(
            PAYLOAD,
            year=2026,
            month=9,
            pair="USD/JPY",
            today_jst=date(2026, 9, 27),
            fetched_at="2026-09-27T06:00:00+09:00",
        )
        self.assertEqual(len(records), 2)
        thursday = records[0]
        friday = records[1]
        self.assertEqual(thursday.unit, 10_000)
        self.assertEqual(thursday.swap_currency, "JPY")
        self.assertEqual(thursday.long_swap_jpy, 88.6077)
        self.assertEqual(thursday.short_swap_jpy, -156.1211)
        self.assertEqual(thursday.effective_date, date(2026, 9, 25))
        self.assertEqual(thursday.status, "confirmed")
        self.assertEqual(friday.effective_date, date(2026, 9, 28))
        self.assertEqual(friday.status, "scheduled")

    def test_special_jpy_pairs_use_100k_publication_unit(self):
        records = parse_month_payload(
            PAYLOAD[:1],
            year=2026,
            month=9,
            pair="ZAR/JPY",
            today_jst=date(2026, 9, 27),
            fetched_at="2026-09-27T06:00:00+09:00",
        )
        self.assertEqual(records[0].unit, 100_000)


if __name__ == "__main__":
    unittest.main()
