from unittest.mock import Mock
import unittest

from truerate.margins import fetch_saxo_margin_rates


class FakeSession:
    def __init__(self, text):
        self.headers = {}
        self.text = text

    def get(self, url, timeout=30):
        response = Mock()
        response.text = self.text
        response.raise_for_status = Mock()
        return response


class SaxoMarginTest(unittest.TestCase):
    def test_pair_specific_rates(self):
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        valid = []
        for i in range(130):
            a = alphabet[(i // 26) % 26] + alphabet[i % 26] + "A"
            b = alphabet[(i // 13) % 26] + alphabet[(i * 3) % 26] + "B"
            valid.append(f"<tr><td>{a}{b}</td><td>X</td><td>4.0%</td></tr>")
        html = "<table>" + "".join(valid) + \
            "<tr><td>GBPJPY</td><td>X</td><td>5.0%</td></tr>" + \
            "<tr><td>USDTRY</td><td>X</td><td>25.0%</td></tr></table>"
        rates = fetch_saxo_margin_rates(session=FakeSession(html))
        self.assertEqual(rates["GBP/JPY"], 0.05)
        self.assertEqual(rates["USD/TRY"], 0.25)


if __name__ == "__main__":
    unittest.main()
