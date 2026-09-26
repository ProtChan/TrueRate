from datetime import date
import unittest

from truerate.brokers.gmo_gaika import parse_calendar_html


HTML = """
<html><body>
<table>
  <thead>
    <tr>
      <th rowspan="2">取引日</th>
      <th colspan="3">USD/JPY</th>
      <th colspan="3">EUR/USD</th>
    </tr>
    <tr>
      <th>SP日数</th><th>買</th><th>売</th>
      <th>SP日数</th><th>買</th><th>売</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>9月9日(水)</td>
      <td>3</td><td>339.0</td><td>-339.0</td>
      <td>3</td><td>-204.0</td><td>204.0</td>
    </tr>
    <tr>
      <td>9月10日(木)</td>
      <td>1</td><td>113.0</td><td>-113.0</td>
      <td>1</td><td>-68.0</td><td>68.0</td>
    </tr>
  </tbody>
</table>
</body></html>
"""


class GmoGaikaParserTest(unittest.TestCase):
    def test_swap_is_effective_on_following_jst_day(self):
        records = parse_calendar_html(
            HTML,
            2026,
            9,
            today_jst=date(2026, 9, 10),
            fetched_at="2026-09-10T09:00:00+09:00",
        )
        usd = next(
            item for item in records
            if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 9)
        )
        self.assertEqual(usd.effective_date, date(2026, 9, 10))
        self.assertEqual(usd.long_swap_jpy, 339.0)
        self.assertEqual(usd.short_swap_jpy, -339.0)
        self.assertEqual(usd.status, "confirmed")

    def test_populated_future_trade_day_is_still_scheduled(self):
        records = parse_calendar_html(
            HTML,
            2026,
            9,
            today_jst=date(2026, 9, 10),
            fetched_at="2026-09-10T09:00:00+09:00",
        )
        usd = next(
            item for item in records
            if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 10)
        )
        self.assertEqual(usd.effective_date, date(2026, 9, 11))
        self.assertEqual(usd.status, "scheduled")

    def test_parses_multiple_pairs_from_same_desktop_table(self):
        records = parse_calendar_html(
            HTML,
            2026,
            9,
            today_jst=date(2026, 9, 12),
            fetched_at="2026-09-12T09:00:00+09:00",
        )
        pairs = {item.pair for item in records}
        self.assertEqual(pairs, {"USD/JPY", "EUR/USD"})


if __name__ == "__main__":
    unittest.main()
