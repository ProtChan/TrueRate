from datetime import date
import unittest

from truerate.brokers.oanda_tokyo import parse_history_csv


CSV_TEXT = """TradeDate,Symbol,SwapLong,SwapShort
2026-09-24,USD/JPY,36.8,-306.4
2026-09-24,EUR/USD,-0.583,0.345
2026-09-25,USD/TRY,-433.115,346.568
"""


class OandaTokyoParserTest(unittest.TestCase):
    def test_jpy_pair_is_normalized_and_moves_to_next_business_day(self):
        records = parse_history_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 27),
            fetched_at="2026-09-27T01:00:00+09:00",
        )
        usd = next(item for item in records if item.pair == "USD/JPY")
        self.assertEqual(usd.unit, 10_000)
        self.assertEqual(usd.swap_currency, "JPY")
        self.assertEqual(usd.long_swap_jpy, 36.8)
        self.assertEqual(usd.short_swap_jpy, -306.4)
        self.assertEqual(usd.effective_date, date(2026, 9, 25))
        self.assertEqual(usd.status, "confirmed")

    def test_cross_pair_keeps_quote_currency(self):
        records = parse_history_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 27),
            fetched_at="2026-09-27T01:00:00+09:00",
        )
        eurusd = next(item for item in records if item.pair == "EUR/USD")
        self.assertEqual(eurusd.swap_currency, "USD")
        self.assertEqual(eurusd.long_swap_jpy, -0.583)
        self.assertEqual(eurusd.short_swap_jpy, 0.345)

    def test_friday_row_is_scheduled_for_monday(self):
        records = parse_history_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 27),
            fetched_at="2026-09-27T01:00:00+09:00",
        )
        usdtry = next(item for item in records if item.pair == "USD/TRY")
        self.assertEqual(usdtry.swap_currency, "TRY")
        self.assertEqual(usdtry.effective_date, date(2026, 9, 28))
        self.assertEqual(usdtry.status, "scheduled")

    def test_blank_side_is_preserved_as_unavailable(self):
        records = parse_history_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 27),
            fetched_at="2026-09-27T01:00:00+09:00",
        )
        row = next(item for item in records if item.pair == "NZD/TRY")
        self.assertIsNone(row.long_swap_jpy)
        self.assertEqual(row.short_swap_jpy, 215.4)
        self.assertEqual(row.status, "unavailable")


if __name__ == "__main__":
    unittest.main()
