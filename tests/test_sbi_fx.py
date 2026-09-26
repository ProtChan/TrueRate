from datetime import date
import unittest

from truerate.brokers.sbi_fx import parse_month_html


HTML = """
<table>
<tr>
<td>09月01日 (火)<br>6:00～翌5:30</td>
<td class="td_commodity_USDJPY">1</td>
<td class="td_commodity_USDJPY">09月03日</td>
<td class="td_commodity_USDJPY">-125</td>
<td class="td_commodity_USDJPY">117</td>
<td class="td_commodity_MXNJPY">1</td>
<td class="td_commodity_MXNJPY">09月03日</td>
<td class="td_commodity_MXNJPY">-1.5</td>
<td class="td_commodity_MXNJPY">1.4</td>
</tr>
</table>
"""


class SbiParserTest(unittest.TestCase):
    def test_parses_buy_sell_and_special_100k_display(self):
        records = parse_month_html(
            HTML,
            2026,
            9,
            today_jst=date(2026, 9, 2),
            fetched_at="2026-09-02T09:00:00+09:00",
        )
        usd = next(item for item in records if item.pair == "USD/JPY")
        mxn = next(item for item in records if item.pair == "MXN/JPY")

        self.assertEqual(usd.effective_date, date(2026, 9, 2))
        self.assertEqual(usd.long_swap_jpy, 117.0)
        self.assertEqual(usd.short_swap_jpy, -125.0)
        self.assertEqual(usd.unit, 10_000)

        self.assertEqual(mxn.long_swap_jpy, 14.0)
        self.assertEqual(mxn.short_swap_jpy, -15.0)
        self.assertEqual(mxn.unit, 100_000)


if __name__ == "__main__":
    unittest.main()
