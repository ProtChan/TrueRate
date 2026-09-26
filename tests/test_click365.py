from datetime import date
import unittest

from truerate.brokers.click365 import parse_summary_csv


CSV_TEXT = """期間指定,2026/09/23～2026/09/24
通貨ペア,"USD/JPY,HUF/JPY,EUR/USD"
商品名,商品タイプ,取引日,スワップポイント
USD/JPY,"U.S. Dollar-Japanese Yen",2026/09/23,384
USD/JPY,"U.S. Dollar-Japanese Yen",2026/09/24,128
HUF/JPY,"Hungarian Forint-Japanese Yen",2026/09/24,5
EUR/USD,"Euro-U.S. Dollar",2026/09/24,-0.460
"""


class Click365ParserTest(unittest.TestCase):
    def test_signed_swap_units_and_d_plus_one(self):
        records = parse_summary_csv(
            CSV_TEXT,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        usd = next(item for item in records if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 24))
        huf = next(item for item in records if item.pair == "HUF/JPY")
        eurusd = next(item for item in records if item.pair == "EUR/USD")

        self.assertEqual(usd.long_swap_jpy, 128.0)
        self.assertEqual(usd.short_swap_jpy, -128.0)
        self.assertEqual(usd.unit, 10_000)
        self.assertEqual(usd.effective_date, date(2026, 9, 25))

        self.assertEqual(huf.unit, 100_000)
        self.assertEqual(huf.long_swap_jpy, 5.0)

        self.assertEqual(eurusd.swap_currency, "USD")
        self.assertEqual(eurusd.long_swap_jpy, -0.46)
        self.assertEqual(eurusd.short_swap_jpy, 0.46)


if __name__ == "__main__":
    unittest.main()
