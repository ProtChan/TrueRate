from datetime import date
import unittest

from truerate.brokers.lightfx import BROKER_ID, LIGHT_BROKER_ID
from truerate.brokers.minfx import parse_calendar_html


HTML = """
<div id="symbol5"><table>
<thead><tr><th>取引日</th><th></th><th>TRYJPY LIGHT</th></tr></thead>
<tbody>
<tr><td>09/25 (金)</td><td>付与日数</td><td>1</td></tr>
<tr><td>買</td><td>24.2</td></tr>
<tr><td>売</td><td>-24.2</td></tr>
</tbody></table></div>
<div id="symbol1"><table>
<thead><tr><th>取引日</th><th></th><th>TRYJPY</th></tr></thead>
<tbody>
<tr><td>09/25 (金)</td><td>付与日数</td><td>1</td></tr>
<tr><td>買</td><td>24.1</td></tr>
<tr><td>売</td><td>-24.1</td></tr>
</tbody></table></div>
"""


class LightFxParserTest(unittest.TestCase):
    def test_standard_and_light_are_distinct_products(self):
        standard = parse_calendar_html(
            HTML,
            today_jst=date(2026, 9, 26),
            broker_id=BROKER_ID,
            source_url="fixture",
        )
        light = parse_calendar_html(
            HTML,
            today_jst=date(2026, 9, 26),
            broker_id=LIGHT_BROKER_ID,
            light_only=True,
            source_url="fixture",
        )
        self.assertEqual(standard[0].broker, BROKER_ID)
        self.assertEqual(standard[0].long_swap_jpy, 24.1)
        self.assertEqual(light[0].broker, LIGHT_BROKER_ID)
        self.assertEqual(light[0].long_swap_jpy, 24.2)


if __name__ == "__main__":
    unittest.main()
