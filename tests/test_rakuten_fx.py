from datetime import date
import unittest

from truerate.brokers.rakuten_fx import parse_swap_data


def fixture_text() -> str:
    lines = ["2026/09/26 22:51:11", "0"]
    while len(lines) <= 39:
        lines.append("")
    lines[2] = "1\t-116\t111\t20260925"
    lines[6] = "5\t25\t-53\t20260925"
    lines[30] = "29\t-2\t1\t20260925"
    return "\n".join(lines)


class RakutenFxParserTest(unittest.TestCase):
    def test_maps_sell_buy_and_friday_to_monday(self):
        records = parse_swap_data(
            fixture_text(),
            today_jst=date(2026, 9, 28),
            fetched_at="2026-09-28T09:00:00+09:00",
            source_url="fixture",
        )
        usd = next(item for item in records if item.pair == "USD/JPY")
        self.assertEqual(usd.long_swap_jpy, 111.0)
        self.assertEqual(usd.short_swap_jpy, -116.0)
        self.assertEqual(usd.unit, 10_000)
        self.assertEqual(usd.trade_date, date(2026, 9, 25))
        self.assertEqual(usd.effective_date, date(2026, 9, 28))
        self.assertEqual(usd.status, "confirmed")
        self.assertEqual(usd.swap_currency, "JPY")

    def test_cross_pair_uses_quote_currency(self):
        records = parse_swap_data(
            fixture_text(),
            today_jst=date(2026, 9, 28),
            source_url="fixture",
        )
        eurusd = next(item for item in records if item.pair == "EUR/USD")
        self.assertEqual(eurusd.long_swap_jpy, -53.0)
        self.assertEqual(eurusd.short_swap_jpy, 25.0)
        self.assertEqual(eurusd.swap_currency, "USD")

    def test_new_pair_mapping(self):
        records = parse_swap_data(
            fixture_text(),
            today_jst=date(2026, 9, 28),
            source_url="fixture",
        )
        huf = next(item for item in records if item.pair == "HUF/JPY")
        self.assertEqual(huf.long_swap_jpy, 1.0)
        self.assertEqual(huf.short_swap_jpy, -2.0)


if __name__ == "__main__":
    unittest.main()
