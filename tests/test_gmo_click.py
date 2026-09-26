from datetime import date
import unittest

from truerate.brokers.gmo_click import parse_calendar_html


HTML = """
<html><body>
<table>
  <thead>
    <tr><th>取引日</th><th>売Swap</th><th>買Swap</th><th>付与日数</th></tr>
  </thead>
  <tbody>
    <tr><td>9月9日(水)</td><td>-321</td><td>321</td><td>3</td></tr>
    <tr><td>9月10日(木)</td><td>-108</td><td>108</td><td>1</td></tr>
    <tr><td>9月11日(金)</td><td></td><td></td><td>1</td></tr>
  </tbody>
</table>
</body></html>
"""


class GmoClickParserTest(unittest.TestCase):
    def test_buy_sell_mapping_and_following_day_effective_date(self):
        records = parse_calendar_html(
            HTML,
            2026,
            9,
            "USD/JPY",
            today_jst=date(2026, 9, 10),
            fetched_at="2026-09-10T09:00:00+09:00",
        )
        row = next(item for item in records if item.trade_date == date(2026, 9, 9))
        self.assertEqual(row.long_swap_jpy, 321.0)
        self.assertEqual(row.short_swap_jpy, -321.0)
        self.assertEqual(row.effective_date, date(2026, 9, 10))
        self.assertEqual(row.status, "confirmed")
        self.assertEqual(row.unit, 10_000)

    def test_future_or_unpopulated_amount_is_scheduled(self):
        records = parse_calendar_html(
            HTML,
            2026,
            9,
            "USD/JPY",
            today_jst=date(2026, 9, 10),
            fetched_at="2026-09-10T09:00:00+09:00",
        )
        future = next(item for item in records if item.trade_date == date(2026, 9, 10))
        blank = next(item for item in records if item.trade_date == date(2026, 9, 11))
        self.assertEqual(future.status, "scheduled")
        self.assertEqual(blank.status, "scheduled")
        self.assertIsNone(blank.long_swap_jpy)
        self.assertIsNone(blank.short_swap_jpy)

    def test_high_notional_pairs_keep_broker_publication_unit(self):
        records = parse_calendar_html(
            HTML,
            2026,
            9,
            "HUF/JPY",
            today_jst=date(2026, 9, 12),
            fetched_at="2026-09-12T09:00:00+09:00",
        )
        self.assertEqual(records[0].unit, 100_000)


if __name__ == "__main__":
    unittest.main()
