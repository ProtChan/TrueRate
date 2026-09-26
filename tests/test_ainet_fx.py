from datetime import date
import unittest

from truerate.brokers.ainet_fx import (
    BROKER_ID,
    LOOP_BROKER_ID,
    LOOP_PAIRS,
    REGULAR_PAIRS,
    parse_page_text,
)


PAGE0 = """
スワップカレンダー2026年9月
通貨ペア USD/JPY EUR/JPY GBP/JPY AUD/JPY NZD/JPY
日付 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買
2026 / 09 / 24 木 1 -140 125 1 -90 75 1 -155 130 1 -125 110 1 -50 10
2026 / 09 / 25 金 1 -140 125 1 -90 75 1 -155 130 1 -125 110 1 -50 10
2026 / 09 / 26 土 - - - - -
2026 / 09 / 29 火 1 - - 1 - - 1 - - 1 - - 1 - -
"""

PAGE4 = """
スワップカレンダー2026年9月
通貨ペア NZD/USD USD/CAD USD/CHF ZAR/JPY TRY/JPY MXN/JPY
日付 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買 付与日数 売 買
2026 / 09 / 24 木 1 25 -60 3 -255 90 1 -205 105 1 -15 10 1 -30 10 1 -20 7
2026 / 09 / 25 金 1 25 -60 1 -85 30 1 -205 105 1 -15 10 1 -30 10 1 -20 7
"""


class AinetParserTest(unittest.TestCase):
    def test_regular_parses_buy_sell_and_business_day(self):
        records = parse_page_text(
            PAGE0,
            page_index=0,
            broker_id=BROKER_ID,
            allowed_pairs=REGULAR_PAIRS,
            today_jst=date(2026, 9, 28),
            fetched_at="2026-09-28T09:00:00+09:00",
        )
        usd_24 = next(r for r in records if r.pair == "USD/JPY" and r.trade_date == date(2026, 9, 24))
        usd_25 = next(r for r in records if r.pair == "USD/JPY" and r.trade_date == date(2026, 9, 25))
        self.assertEqual(usd_24.long_swap_jpy, 125.0)
        self.assertEqual(usd_24.short_swap_jpy, -140.0)
        self.assertEqual(usd_24.effective_date, date(2026, 9, 25))
        self.assertEqual(usd_25.effective_date, date(2026, 9, 28))
        self.assertEqual(usd_25.unit, 10_000)

    def test_future_blank_amounts_are_scheduled(self):
        records = parse_page_text(
            PAGE0,
            page_index=0,
            broker_id=BROKER_ID,
            allowed_pairs=REGULAR_PAIRS,
            today_jst=date(2026, 9, 28),
        )
        future = next(r for r in records if r.pair == "USD/JPY" and r.trade_date == date(2026, 9, 29))
        self.assertIsNone(future.long_swap_jpy)
        self.assertIsNone(future.short_swap_jpy)
        self.assertEqual(future.status, "scheduled")

    def test_regular_and_loop_pair_sets_are_distinct(self):
        regular = parse_page_text(
            PAGE4,
            page_index=4,
            broker_id=BROKER_ID,
            allowed_pairs=REGULAR_PAIRS,
            today_jst=date(2026, 9, 28),
        )
        loop = parse_page_text(
            PAGE4,
            page_index=4,
            broker_id=LOOP_BROKER_ID,
            allowed_pairs=LOOP_PAIRS,
            today_jst=date(2026, 9, 28),
        )
        self.assertNotIn("TRY/JPY", {r.pair for r in regular})
        self.assertNotIn("MXN/JPY", {r.pair for r in regular})
        self.assertIn("TRY/JPY", {r.pair for r in loop})
        self.assertIn("MXN/JPY", {r.pair for r in loop})
        self.assertEqual({r.broker for r in loop}, {LOOP_BROKER_ID})


if __name__ == "__main__":
    unittest.main()
