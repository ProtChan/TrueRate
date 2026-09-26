from datetime import date
import unittest

from truerate.brokers.hirose import parse_history_csv


CSV_TEXT = """日付,USD/JPY,,EUR/USD,,大口USD/JPY,
,売り,買い,売り,買い,売り,買い
2021/01/04,-8.3,0.2,0.022,-0.042,-8.0,0.1
2021/01/05,-8.3,0.2,0.023,-0.043,-8.0,0.1
"""


class HiroseParserTest(unittest.TestCase):
    def test_quote_currency_and_units(self):
        records = parse_history_csv(
            CSV_TEXT,
            today_jst=date(2021, 1, 6),
            fetched_at="2021-01-06T09:00:00+09:00",
        )
        usd_jpy = next(item for item in records if item.pair == "USD/JPY")
        eur_usd = next(item for item in records if item.pair == "EUR/USD")
        self.assertEqual(usd_jpy.unit, 1_000)
        self.assertEqual(usd_jpy.swap_currency, "JPY")
        self.assertEqual(usd_jpy.long_swap_jpy, 0.2)
        self.assertEqual(eur_usd.swap_currency, "USD")
        self.assertEqual(eur_usd.short_swap_jpy, 0.022)
        self.assertEqual(eur_usd.long_swap_jpy, -0.042)
        self.assertEqual(eur_usd.effective_date, date(2021, 1, 5))
        self.assertNotIn("大口USD/JPY", {item.pair for item in records})


if __name__ == "__main__":
    unittest.main()
