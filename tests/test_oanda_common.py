from datetime import date
import unittest

from truerate.brokers.oanda_common import (
    complete_supported_records,
    currently_unavailable_pairs,
)
from truerate.models import SwapRecord


def record(pair, trade_date, long_swap, short_swap):
    return SwapRecord(
        broker="oanda_ny",
        pair=pair,
        trade_date=trade_date,
        effective_date=trade_date,
        sp_days=1,
        long_swap_jpy=long_swap,
        short_swap_jpy=short_swap,
        unit=10_000,
        status="confirmed" if long_swap is not None and short_swap is not None else "unavailable",
        source="fixture",
        fetched_at="2026-09-27T09:00:00+09:00",
    )


class OandaAvailabilityTest(unittest.TestCase):
    def test_latest_blank_side_excludes_entire_pair(self):
        rows = [
            record("USD/TRY", date(2026, 9, 24), -430.0, 345.0),
            record("USD/TRY", date(2026, 9, 25), None, 350.0),
            record("EUR/USD", date(2026, 9, 25), -70.0, 68.0),
        ]
        unavailable = currently_unavailable_pairs(rows, today=date(2026, 9, 27))
        self.assertEqual(unavailable, {"USD/TRY"})

        kept = complete_supported_records(rows, unavailable_pairs=unavailable)
        self.assertEqual({row.pair for row in kept}, {"EUR/USD"})

    def test_future_blank_does_not_remove_pair_early(self):
        rows = [
            record("USD/TRY", date(2026, 9, 25), -430.0, 345.0),
            record("USD/TRY", date(2026, 9, 28), None, 350.0),
        ]
        unavailable = currently_unavailable_pairs(rows, today=date(2026, 9, 27))
        self.assertEqual(unavailable, set())


if __name__ == "__main__":
    unittest.main()
