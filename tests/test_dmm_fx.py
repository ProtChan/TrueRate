from datetime import date
import unittest

from truerate.brokers.dmm_fx import (
    BROKER_ID,
    BROKER_LARGE_ID,
    BROKER_MINI_ID,
    parse_pair_payload,
)


class DmmFxParserTest(unittest.TestCase):
    def test_standard_pair_uses_display_date_as_effective_date(self):
        payload = {
            "body": {
                "swap": [
                    {
                        "fxProductId": "USD/JPY",
                        "buySwapAmount": "119",
                        "sellSwapAmount": "-122",
                        "swapAmountUnit": "10000",
                        "eventYmdDate": "20260925",
                        "givingDays": "1",
                    }
                ]
            }
        }
        records = parse_pair_payload(
            payload,
            code="USD_JPY",
            broker=BROKER_ID,
            today_jst=date(2026, 9, 25),
            fetched_at="2026-09-28T09:00:00+09:00",
        )
        row = records[0]
        self.assertEqual(row.pair, "USD/JPY")
        self.assertEqual(row.long_swap_jpy, 119.0)
        self.assertEqual(row.short_swap_jpy, -122.0)
        self.assertEqual(row.unit, 10_000)
        self.assertEqual(row.effective_date, date(2026, 9, 25))
        self.assertEqual(row.status, "confirmed")
        self.assertEqual(row.swap_currency, "JPY")

    def test_mini_maps_synthetic_code_to_real_pair_and_1k_unit(self):
        payload = {
            "body": {
                "swap": [
                    {
                        "fxProductId": "USM/JPY",
                        "buySwapAmount": "11",
                        "sellSwapAmount": "-12",
                        "swapAmountUnit": "1000",
                        "eventYmdDate": "20260924",
                        "givingDays": "1",
                    }
                ]
            }
        }
        row = parse_pair_payload(
            payload,
            code="USM_JPY",
            broker=BROKER_MINI_ID,
            today_jst=date(2026, 9, 25),
        )[0]
        self.assertEqual(row.pair, "USD/JPY")
        self.assertEqual(row.unit, 1_000)
        self.assertEqual(row.long_swap_jpy, 11.0)

    def test_large_maps_synthetic_code_to_real_pair(self):
        payload = {
            "body": {
                "swap": [
                    {
                        "fxProductId": "AUL/JPY",
                        "buySwapAmount": "104",
                        "sellSwapAmount": "-107",
                        "swapAmountUnit": "10000",
                        "eventYmdDate": "20260924",
                        "givingDays": "1",
                    }
                ]
            }
        }
        row = parse_pair_payload(
            payload,
            code="AUL_JPY",
            broker=BROKER_LARGE_ID,
            today_jst=date(2026, 9, 25),
        )[0]
        self.assertEqual(row.pair, "AUD/JPY")
        self.assertEqual(row.unit, 10_000)

    def test_future_effective_date_is_scheduled(self):
        payload = {
            "body": {
                "swap": [
                    {
                        "fxProductId": "EUR/USD",
                        "buySwapAmount": "-73",
                        "sellSwapAmount": "70",
                        "swapAmountUnit": "10000",
                        "eventYmdDate": "20260928",
                        "givingDays": "1",
                    }
                ]
            }
        }
        row = parse_pair_payload(
            payload,
            code="EUR_USD",
            broker=BROKER_ID,
            today_jst=date(2026, 9, 26),
        )[0]
        self.assertEqual(row.status, "scheduled")
        self.assertEqual(row.swap_currency, "JPY")


if __name__ == "__main__":
    unittest.main()
