from datetime import date
import unittest

from truerate.brokers.gmo_click import PAIR_START_DATES, parse_calendar_html


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

DUAL_CURRENCY_HTML = """
<html><body>
<table>
  <thead>
    <tr><th>取引日</th><th>売Swap</th><th>買Swap</th><th>付与日数</th></tr>
  </thead>
  <tbody>
    <tr><td>5月1日(金)</td><td>33 $0.21</td><td>-33 -$0.21</td><td>1</td></tr>
    <tr><td>5月6日(水)</td><td>96 $0.63</td><td>-96 -$0.63</td><td>3</td></tr>
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

    def test_dual_currency_cells_use_jpy_amount(self):
        records = parse_calendar_html(
            DUAL_CURRENCY_HTML,
            2026,
            5,
            "NZD/USD",
            today_jst=date(2026, 5, 8),
            fetched_at="2026-05-08T09:00:00+09:00",
        )
        first = records[0]
        self.assertEqual(first.short_swap_jpy, 33.0)
        self.assertEqual(first.long_swap_jpy, -33.0)
        self.assertEqual(first.unit, 10_000)
        self.assertEqual(records[1].short_swap_jpy, 96.0)
        self.assertEqual(records[1].long_swap_jpy, -96.0)

    def test_2025_added_pairs_have_explicit_start_date(self):
        self.assertEqual(PAIR_START_DATES["CZK/JPY"], date(2025, 3, 17))
        self.assertEqual(PAIR_START_DATES["PLN/JPY"], date(2025, 3, 17))
        self.assertEqual(PAIR_START_DATES["HUF/JPY"], date(2025, 3, 17))
        self.assertEqual(PAIR_START_DATES["AUD/NZD"], date(2025, 3, 17))

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
