from datetime import date
import unittest

from truerate.models import next_business_day_after


class EffectiveDateTest(unittest.TestCase):
    def test_weekday_moves_to_following_day(self):
        self.assertEqual(
            next_business_day_after(date(2026, 9, 24)),
            date(2026, 9, 25),
        )

    def test_friday_moves_to_monday(self):
        self.assertEqual(
            next_business_day_after(date(2026, 9, 25)),
            date(2026, 9, 28),
        )

    def test_weekend_moves_to_monday(self):
        self.assertEqual(
            next_business_day_after(date(2026, 9, 26)),
            date(2026, 9, 28),
        )
        self.assertEqual(
            next_business_day_after(date(2026, 9, 27)),
            date(2026, 9, 28),
        )


if __name__ == "__main__":
    unittest.main()
