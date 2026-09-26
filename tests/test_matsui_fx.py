from datetime import date
import unittest

from truerate.brokers.matsui_fx import parse_year_csv


CSV_TEXT = """通貨ペア,取引日,付与日数,売(円),買(円),年額売（円）,年率売（%）,年額買（円）,年率売（%）
米ドル/円,2026/9/24,1,-151,143,,,,
米ドル/円,2026/9/25,1,-151,143,,,,
ユーロ/NZドル,2026/9/24,3,120,-180,,,,
ハンガリー/円,2026/9/24,1,-8,5,,,,
米ドル/円,2026/9/26,-,-,-,,,,
"""


class MatsuiFxParserTest(unittest.TestCase):
    def test_maps_pair_buy_sell_and_d_plus_one(self):
        records = parse_year_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        usd = next(item for item in records if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 24))
        self.assertEqual(usd.long_swap_jpy, 143.0)
        self.assertEqual(usd.short_swap_jpy, -151.0)
        self.assertEqual(usd.unit, 10_000)
        self.assertEqual(usd.effective_date, date(2026, 9, 25))
        self.assertEqual(usd.status, "confirmed")

    def test_cross_pair_is_jpy_cashflow(self):
        records = parse_year_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        eurnzd = next(item for item in records if item.pair == "EUR/NZD")
        self.assertEqual(eurnzd.swap_currency, "JPY")
        self.assertEqual(eurnzd.long_swap_jpy, -180.0)
        self.assertEqual(eurnzd.short_swap_jpy, 120.0)


if __name__ == "__main__":
    unittest.main()
