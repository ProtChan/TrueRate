from datetime import date
import unittest

from truerate.brokers.minfx import parse_calendar_html


HTML = """
<div id="symbol1">
<table>
  <thead><tr><th>取引日</th><th></th><th>USDJPY</th><th>HUFJPY</th></tr></thead>
  <tbody>
    <tr><td>09/25 (金)</td><td>付与日数</td><td>1</td><td>1</td></tr>
    <tr><td>買</td><td>118.0</td><td>6.0</td></tr>
    <tr><td>売</td><td>-118.0</td><td>-6.0</td></tr>
    <tr><td>09/26 (土)</td><td>付与日数</td><td>-</td><td>-</td></tr>
    <tr><td>買</td><td>-</td><td>-</td></tr>
    <tr><td>売</td><td>-</td><td>-</td></tr>
  </tbody>
</table>
</div>
<div id="symbol3">
<table>
  <thead><tr><th>取引日</th><th></th><th>EURUSD LIGHT LIGHT</th><th>EURUSD</th></tr></thead>
  <tbody>
    <tr><td>09/25 (金)</td><td>付与日数</td><td>1</td><td>1</td></tr>
    <tr><td>買</td><td>-69.3</td><td>-69.3</td></tr>
    <tr><td>売</td><td>69.2</td><td>69.2</td></tr>
  </tbody>
</table>
</div>
<div id="symbol6">
<table>
  <thead><tr><th>取引日</th><th></th><th>CHFTRY</th></tr></thead>
  <tbody>
    <tr><td>09/25 (金)</td><td>付与日数</td><td>1</td></tr>
    <tr><td>買</td><td>-1399.9</td></tr>
    <tr><td>売</td><td>1394.6</td></tr>
  </tbody>
</table>
</div>
"""


class MinFxParserTest(unittest.TestCase):
    def test_maps_standard_pair_buy_sell_and_d_plus_one(self):
        records = parse_calendar_html(
            HTML,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        usd = next(item for item in records if item.pair == "USD/JPY")
        self.assertEqual(usd.trade_date, date(2026, 9, 25))
        self.assertEqual(usd.effective_date, date(2026, 9, 26))
        self.assertEqual(usd.long_swap_jpy, 118.0)
        self.assertEqual(usd.short_swap_jpy, -118.0)
        self.assertEqual(usd.status, "confirmed")
        self.assertEqual(usd.unit, 10_000)

    def test_huf_uses_100k_publication_unit(self):
        records = parse_calendar_html(
            HTML,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        huf = next(item for item in records if item.pair == "HUF/JPY")
        self.assertEqual(huf.unit, 100_000)
        self.assertEqual(huf.long_swap_jpy, 6.0)

    def test_excludes_light_variant_and_keeps_standard(self):
        records = parse_calendar_html(
            HTML,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        eur = [item for item in records if item.pair == "EUR/USD"]
        self.assertEqual(len(eur), 1)
        self.assertEqual(eur[0].long_swap_jpy, -69.3)

    def test_parses_high_value_chf_try(self):
        records = parse_calendar_html(
            HTML,
            today_jst=date(2026, 9, 26),
            fetched_at="2026-09-26T09:00:00+09:00",
        )
        chftry = next(item for item in records if item.pair == "CHF/TRY")
        self.assertEqual(chftry.long_swap_jpy, -1399.9)
        self.assertEqual(chftry.short_swap_jpy, 1394.6)


if __name__ == "__main__":
    unittest.main()
