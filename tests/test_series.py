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
                "swap_currency": "JPY",
            }
        ]
        rates = [
            {"date": "2026-09-09", "currency": "JPY", "per_usd": "150.0", "provider": "fixture"},
            {"date": "2026-09-10", "currency": "JPY", "per_usd": "150.0", "provider": "fixture"},
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

    def test_quote_currency_swap_is_converted_to_jpy(self):
        swaps = [
            {
                "broker": "hirose",
                "pair": "EUR/USD",
                "trade_date": "2026-09-09",
                "effective_date": "2026-09-10",
                "sp_days": "0",
                "long_swap_jpy": "1.0",
                "short_swap_jpy": "-1.0",
                "unit": "10000",
                "status": "confirmed",
                "source": "fixture",
                "fetched_at": "2026-09-10T09:00:00+09:00",
                "swap_currency": "USD",
            }
        ]
        rates = [
            {"date": "2026-09-09", "currency": "JPY", "per_usd": "150.0", "provider": "fixture"},
            {"date": "2026-09-10", "currency": "JPY", "per_usd": "150.0", "provider": "fixture"},
            {"date": "2026-09-09", "currency": "EUR", "per_usd": "0.85", "provider": "fixture"},
            {"date": "2026-09-10", "currency": "EUR", "per_usd": "0.85", "provider": "fixture"},
        ]

        payload = build_site_payload(
            swaps,
            rates,
            generated_at="2026-09-10T09:15:00+09:00",
            today=date(2026, 9, 10),
        )
        last = payload["series"]["EUR/USD"]["hirose"]["points"][-1]
        self.assertEqual(last["cum_long_swap_jpy"], 150.0)
        self.assertEqual(last["cum_short_swap_jpy"], -150.0)


if __name__ == "__main__":
    unittest.main()
