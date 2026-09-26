from unittest.mock import Mock
import unittest

from truerate.margins import fetch_oanda_ny_margin_rates


HTML = """
<table>
<tr><th>取引通貨ペア コード</th><th>名称</th><th>証拠金率</th></tr>
<tr><td>USD/JPY</td><td>米ドル/円</td><td>4%</td></tr>
<tr><td>GBP/JPY</td><td>英ポンド/円</td><td>5%</td></tr>
<tr><td>USD/TRY</td><td>米ドル/トルコリラ</td><td>25%</td></tr>
</table>
"""


class FakeSession:
    def __init__(self):
        self.headers = {}
    def get(self, url, timeout=30):
        response = Mock()
        response.text = HTML
        response.raise_for_status = Mock()
        return response


class OandaNyMarginTest(unittest.TestCase):
    def test_parser_reads_pair_specific_rates(self):
        # Use the production parser logic against a fixture, while bypassing
        # the production minimum-row sanity check by extending fixture rows.
        html = "<table>" + "".join(
            f"<tr><td>AA{i:02d}/JPY</td><td>X</td><td>4%</td></tr>"
            for i in range(60)
        ) + "<tr><td>GBP/JPY</td><td>X</td><td>5%</td></tr>" +             "<tr><td>USD/TRY</td><td>X</td><td>25%</td></tr></table>"
        session = FakeSession()
        response = Mock()
        response.text = html
        response.raise_for_status = Mock()
        session.get = Mock(return_value=response)
        rates = fetch_oanda_ny_margin_rates(session=session)
        self.assertEqual(rates["GBP/JPY"], 0.05)
        self.assertEqual(rates["USD/TRY"], 0.25)


if __name__ == "__main__":
    unittest.main()
