from datetime import date
import unittest

from truerate.brokers.gaitame_com import parse_month_csv


CSV_TEXT = ''',米ドル/円,,,ハンガリー/円,,,露ルーブル/円,,,スイス/トルコリラ,,
取引日,"付与
日数",買,売,"付与
日数",買,売,"付与
日数",買,売,"付与
日数",買,売
9/23（水）,3,345,-420,3,15,-30,3,0,0,3,-4808,3837
9/24（木）,1,115,-140,1,5,-10,1,0,0,1,-1618,1297
'''


class GaitameComParserTest(unittest.TestCase):
    def test_maps_columns_and_uses_following_day(self):
        records = parse_month_csv(
            CSV_TEXT,
            2026,
            9,
            today_jst=date(2026, 9, 24),
            fetched_at="2026-09-24T09:00:00+09:00",
        )
        usd = next(
            item for item in records
            if item.pair == "USD/JPY" and item.trade_date == date(2026, 9, 23)
        )
        self.assertEqual(usd.sp_days, 3)
        self.assertEqual(usd.long_swap_jpy, 345.0)
        self.assertEqual(usd.short_swap_jpy, -420.0)
        self.assertEqual(usd.effective_date, date(2026, 9, 24))
        self.assertEqual(usd.status, "confirmed")
        self.assertEqual(usd.unit, 10_000)

    def test_huf_calendar_unit_is_100k(self):
        records = parse_month_csv(
            CSV_TEXT,
            2026,
            9,
            today_jst=date(2026, 9, 24),
            fetched_at="2026-09-24T09:00:00+09:00",
        )
        huf = next(item for item in records if item.pair == "HUF/JPY")
        self.assertEqual(huf.unit, 100_000)
        self.assertEqual(huf.long_swap_jpy, 15.0)

    def test_suspended_rub_is_excluded(self):
        records = parse_month_csv(
            CSV_TEXT,
            2026,
            9,
            today_jst=date(2026, 9, 25),
            fetched_at="2026-09-25T09:00:00+09:00",
        )
        self.assertNotIn("RUB/JPY", {item.pair for item in records})

    def test_future_effective_date_is_scheduled(self):
        records = parse_month_csv(
            CSV_TEXT,
            2026,
            9,
            today_jst=date(2026, 9, 24),
            fetched_at="2026-09-24T09:00:00+09:00",
        )
        chftry = next(
            item for item in records
            if item.pair == "CHF/TRY" and item.trade_date == date(2026, 9, 24)
        )
        self.assertEqual(chftry.effective_date, date(2026, 9, 25))
        self.assertEqual(chftry.status, "scheduled")


if __name__ == "__main__":
    unittest.main()
