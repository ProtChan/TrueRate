from datetime import date
import unittest

from truerate.brokers.saxo_fx import parse_pdf_text


TEXT = """Instrument List / 通貨ペア一覧 発生日 売Swap(円) 買Swap(円) 付与日数
AUDCAD (豪ドル/カナダドル) 2026年9月17日(木) -318.91 81.40 3
TRYJPY (トルコリラ/円) 2026年9月18日(金) -29.00 25.00 1
HUFJPY (ハンガリーフォリント/円) 2026年9月18日(金) -0.76 0.38 1
"""


class SaxoFxParserTest(unittest.TestCase):
    def test_maps_sell_buy_as_jpy_per_10k(self):
        records = parse_pdf_text(
            TEXT,
            today_jst=date(2026, 9, 21),
            fetched_at="2026-09-21T09:00:00+09:00",
        )
        audcad = next(item for item in records if item.pair == "AUD/CAD")
        self.assertEqual(audcad.unit, 10_000)
        self.assertEqual(audcad.swap_currency, "JPY")
        self.assertEqual(audcad.short_swap_jpy, -318.91)
        self.assertEqual(audcad.long_swap_jpy, 81.40)
        self.assertEqual(audcad.sp_days, 3)
        self.assertEqual(audcad.effective_date, date(2026, 9, 18))

    def test_friday_rolls_to_monday(self):
        records = parse_pdf_text(
            TEXT,
            today_jst=date(2026, 9, 21),
            fetched_at="2026-09-21T09:00:00+09:00",
        )
        tr = next(item for item in records if item.pair == "TRY/JPY")
        self.assertEqual(tr.effective_date, date(2026, 9, 21))
        self.assertEqual(tr.long_swap_jpy, 25.0)


if __name__ == "__main__":
    unittest.main()
