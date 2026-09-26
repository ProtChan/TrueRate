from datetime import date
import unittest

from truerate.brokers.fxbroadnet import parse_page_text


PAGE0 = """
スワップポイントカレンダー
2026年8月
8月24日 (月) 8月25日 (火) 1 -51 1 1 -15 7 1 -119 110 1 21 -24 1 -57 40 1 -248 195 1 -62 52 1 -199 125
8月25日 (火) 8月26日 (水) 1 -51 1 1 -15 7 1 -119 110 1 21 -24 1 -57 40 1 -248 195 1 -62 52 1 -199 125
8月29日 (土)
"""


class FxBroadnetParserTest(unittest.TestCase):
    def test_parses_page_order_units_and_d_plus_one(self):
        records = parse_page_text(
            PAGE0,
            year=2026,
            month=8,
            page_index=0,
            today_jst=date(2026, 8, 26),
            fetched_at="2026-08-26T09:00:00+09:00",
        )
        usd = next(item for item in records if item.pair == "USD/JPY" and item.trade_date == date(2026, 8, 24))
        zar = next(item for item in records if item.pair == "ZAR/JPY" and item.trade_date == date(2026, 8, 24))
        self.assertEqual(usd.short_swap_jpy, -51.0)
        self.assertEqual(usd.long_swap_jpy, 1.0)
        self.assertEqual(usd.effective_date, date(2026, 8, 25))
        self.assertEqual(usd.unit, 10_000)
        self.assertEqual(zar.short_swap_jpy, -199.0)
        self.assertEqual(zar.long_swap_jpy, 125.0)
        self.assertEqual(zar.unit, 100_000)

    def test_weekend_without_values_is_ignored(self):
        records = parse_page_text(
            PAGE0,
            year=2026,
            month=8,
            page_index=0,
            today_jst=date(2026, 8, 30),
        )
        self.assertFalse(any(item.trade_date == date(2026, 8, 29) for item in records))


if __name__ == "__main__":
    unittest.main()
