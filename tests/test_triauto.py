from datetime import date
import unittest

from truerate.brokers.triauto import parse_month_payload


DAILY = {
    "20260923": {
        "USDJPY": ["USD/JPY", "-573.0", "345.0"],
        "CHFTRY": ["CHF/TRY", "4,740.0", "-6,540.0"],
        "USD_APJPY": ["USD_AP/JPY", "-573.0", "345.0"],
        "SEKJPY": ["SEK/JPY", "0.0", "0.0"],
    },
    "20260924": {
        "USDJPY": ["USD/JPY", "-194.0", "118.0"],
        "CHFTRY": ["CHF/TRY", "1,550.0", "-2,150.0"],
    },
}
ADD_DAYS = {
    "20260923": {
        "USDJPY": ["2026/9/23", "USD/JPY", "3"],
        "CHFTRY": ["2026/9/23", "CHF/TRY", "3"],
        "USD_APJPY": ["2026/9/23", "USD_AP/JPY", "3"],
        "SEKJPY": ["2026/9/23", "SEK/JPY", "3"],
    },
    "20260924": {
        "USDJPY": ["2026/9/24", "USD/JPY", "1"],
        "CHFTRY": ["2026/9/24", "CHF/TRY", "1"],
    },
}


class TriautoParserTest(unittest.TestCase):
    def test_maps_sell_and_buy_and_uses_following_day(self):
        records = parse_month_payload(
            DAILY,
            ADD_DAYS,
            2026,
            9,
            today_jst=date(2026, 9, 24),
            fetched_at="2026-09-24T09:00:00+09:00",
        )
        usd = next(
            item
            for item in records
            if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 23)
        )
        self.assertEqual(usd.short_swap_jpy, -573.0)
        self.assertEqual(usd.long_swap_jpy, 345.0)
        self.assertEqual(usd.sp_days, 3)
        self.assertEqual(usd.effective_date, date(2026, 9, 24))
        self.assertEqual(usd.status, "confirmed")
        self.assertEqual(usd.unit, 10_000)

    def test_parses_comma_values_for_chf_try(self):
        records = parse_month_payload(
            DAILY,
            ADD_DAYS,
            2026,
            9,
            today_jst=date(2026, 9, 24),
            fetched_at="2026-09-24T09:00:00+09:00",
        )
        chftry = next(
            item
            for item in records
            if item.pair == "CHF/TRY" and item.trade_date == date(2026, 9, 23)
        )
        self.assertEqual(chftry.short_swap_jpy, 4740.0)
        self.assertEqual(chftry.long_swap_jpy, -6540.0)

    def test_future_effective_day_is_scheduled(self):
        records = parse_month_payload(
            DAILY,
            ADD_DAYS,
            2026,
            9,
            today_jst=date(2026, 9, 24),
            fetched_at="2026-09-24T09:00:00+09:00",
        )
        usd = next(
            item
            for item in records
            if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 24)
        )
        self.assertEqual(usd.effective_date, date(2026, 9, 25))
        self.assertEqual(usd.status, "scheduled")

    def test_internal_ap_and_non_public_pairs_are_excluded(self):
        records = parse_month_payload(
            DAILY,
            ADD_DAYS,
            2026,
            9,
            today_jst=date(2026, 9, 25),
            fetched_at="2026-09-25T09:00:00+09:00",
        )
        pairs = [item.pair for item in records]
        self.assertNotIn("USD_AP/JPY", pairs)
        self.assertNotIn("SEK/JPY", pairs)


if __name__ == "__main__":
    unittest.main()
