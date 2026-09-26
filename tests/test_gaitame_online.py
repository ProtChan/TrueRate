from datetime import date
import unittest

from truerate.brokers.gaitame_online import parse_page_text


PAGE0 = """
スワップポイント一覧表2026年9月
通貨ペア USD/JPY EUR/JPY GBP/JPY AUD/JPY NZD/JPY CAD/JPY CHF/JPY
日付 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買
2026 / 09 / 24 木 1 -135 125 1 -85 75 1 -160 135 1 -125 115 1 -55 15 1 -65 40 1 35 -55
2026 / 09 / 25 金 1 -135 125 1 -85 75 1 -160 135 1 -125 115 1 -55 15 2 -130 80 1 35 -55
2026 / 09 / 26 土 - - - - - - -
2026 / 09 / 29 火 1 - - 1 - - 1 - - 1 - - 1 - - 1 - - 1 - -
"""


class GaitameOnlineParserTest(unittest.TestCase):
    def test_parses_buy_sell_and_friday_to_monday(self):
        records = parse_page_text(
            PAGE0,
            page_index=0,
            today_jst=date(2026, 9, 28),
            fetched_at="2026-09-28T09:00:00+09:00",
        )
        usd24 = next(r for r in records if r.pair == "USD/JPY" and r.trade_date == date(2026, 9, 24))
        usd25 = next(r for r in records if r.pair == "USD/JPY" and r.trade_date == date(2026, 9, 25))
        self.assertEqual(usd24.long_swap_jpy, 125.0)
        self.assertEqual(usd24.short_swap_jpy, -135.0)
        self.assertEqual(usd24.effective_date, date(2026, 9, 25))
        self.assertEqual(usd25.effective_date, date(2026, 9, 28))
        self.assertEqual(usd25.unit, 10_000)

    def test_future_blank_values_are_scheduled(self):
        records = parse_page_text(
            PAGE0,
            page_index=0,
            today_jst=date(2026, 9, 28),
        )
        future = next(r for r in records if r.pair == "USD/JPY" and r.trade_date == date(2026, 9, 29))
        self.assertIsNone(future.long_swap_jpy)
        self.assertIsNone(future.short_swap_jpy)
        self.assertEqual(future.status, "scheduled")

    def test_zero_day_forces_zero_cashflow(self):
        text = "2024/1/2 火 0 0 1 0 0 1 0 0 1 0 0 1 0 0 1 0 0 1 0 0 1"
        records = parse_page_text(
            text,
            page_index=0,
            today_jst=date(2024, 1, 3),
        )
        usd = next(r for r in records if r.pair == "USD/JPY")
        self.assertEqual(usd.sp_days, 0)
        self.assertEqual(usd.long_swap_jpy, 0.0)
        self.assertEqual(usd.short_swap_jpy, 0.0)


if __name__ == "__main__":
    unittest.main()
