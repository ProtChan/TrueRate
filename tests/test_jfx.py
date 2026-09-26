from datetime import date
import unittest

from truerate.brokers.jfx import parse_history_csv


CSV_TEXT = """DATE,USD/JPY,,EUR/USD,,MXN/JPY,,HUF/JPY,,大口USD/JPY,
,SELL,BUY,SELL,BUY,SELL,BUY,SELL,BUY,SELL,BUY
20210104,-0.6,0.1,-0.005,-0.007,-5,4,-80,70,-0.6,0.1
20210105,-0.6,0.1,-0.006,-0.008,-5,4,-80,70,-0.6,0.1
"""


class JfxParserTest(unittest.TestCase):
    def test_quote_currency_and_exception_unit(self):
        records = parse_history_csv(
            CSV_TEXT,
            today_jst=date(2021, 1, 6),
            fetched_at="2021-01-06T09:00:00+09:00",
        )
        eur_usd = next(item for item in records if item.pair == "EUR/USD")
        mxn = next(item for item in records if item.pair == "MXN/JPY")
        huf = next(item for item in records if item.pair == "HUF/JPY")
        self.assertEqual(eur_usd.swap_currency, "USD")
        self.assertEqual(eur_usd.long_swap_jpy, -0.007)
        self.assertEqual(mxn.unit, 10_000)
        self.assertEqual(mxn.swap_currency, "JPY")
        self.assertEqual(huf.unit, 100_000)
        self.assertEqual(huf.long_swap_jpy, 70.0)
        self.assertNotIn("大口USD/JPY", {item.pair for item in records})


if __name__ == "__main__":
    unittest.main()
