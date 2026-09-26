from datetime import date
import unittest

from truerate.series import build_site_payload


class SeriesEffectiveDateTest(unittest.TestCase):
    def test_swap_enters_index_on_effective_date_not_trade_date(self):
        swaps = [
            {
                "broker": "gmo_gaika",
                "pair": "USD/JPY",
                "trade_date": "2026-09-09",
                "effective_date": "2026-09-10",
                "sp_days": "3",
                "long_swap_jpy": "339.0",
                "short_swap_jpy": "-339.0",
                "unit": "10000",
                "status": "confirmed",
                "source": "fixture",
                "fetched_at": "2026-09-10T09:00:00+09:00",
            }
        ]
        rates = [
            {
                "date": "2026-09-09",
                "currency": "JPY",
                "per_usd": "150.0",
                "provider": "fixture",
            },
            {
                "date": "2026-09-10",
                "currency": "JPY",
                "per_usd": "150.0",
                "provider": "fixture",
            },
        ]

        payload = build_site_payload(
            swaps,
            rates,
            generated_at="2026-09-10T09:15:00+09:00",
            today=date(2026, 9, 10),
        )
        points = {
            point["date"]: point
            for point in payload["series"]["USD/JPY"]["gmo_gaika"]["points"]
        }

        self.assertEqual(points["2026-09-09"]["cum_long_swap_jpy"], 0.0)
        self.assertEqual(points["2026-09-09"]["cum_short_swap_jpy"], 0.0)
        self.assertEqual(points["2026-09-10"]["cum_long_swap_jpy"], 339.0)
        self.assertEqual(points["2026-09-10"]["cum_short_swap_jpy"], -339.0)


if __name__ == "__main__":
    unittest.main()
