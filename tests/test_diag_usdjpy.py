import csv
from datetime import date, timedelta
from pathlib import Path
import unittest


class DefaultBrokerDiagnostic(unittest.TestCase):
    def test_print_usdjpy_one_year_buy_coverage(self):
        end = date(2026, 9, 27)
        start = end.replace(year=end.year - 1)
        rows = []
        for path in sorted(Path("data/swaps").glob("*.csv")):
            try:
                with path.open(encoding="utf-8", newline="") as handle:
                    data = [
                        row for row in csv.DictReader(handle)
                        if row.get("pair") == "USD/JPY"
                        and row.get("status") == "confirmed"
                        and row.get("long_swap_jpy", "") != ""
                        and row.get("short_swap_jpy", "") != ""
                    ]
            except UnicodeDecodeError:
                continue
            if not data:
                continue
            broker = data[-1]["broker"]
            dates = [date.fromisoformat(row["effective_date"]) for row in data]
            window = [row for row in data if start <= date.fromisoformat(row["effective_date"]) <= end]
            total = 0.0
            for row in window:
                total += float(row["long_swap_jpy"]) * (10000 / int(row["unit"]))
            rows.append((broker, min(dates), max(dates), len(window), round(total, 2), path.name))
        print("\nUSDJPY_1Y_BUY_DIAGNOSTIC")
        for item in sorted(rows, key=lambda item: item[4], reverse=True):
            print(item)
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
