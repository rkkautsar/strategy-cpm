import unittest
from datetime import date

from scripts.monthly_schedule import schedule


class MonthlyScheduleTests(unittest.TestCase):
    def test_last_session_and_weekend(self):
        self.assertEqual(schedule(date(2026, 10, 30)), (True, date(2026, 11, 2)))
        self.assertEqual(schedule(date(2026, 10, 31)), (False, None))

    def test_scheduled_market_holiday(self):
        self.assertEqual(schedule(date(2024, 3, 28)), (True, date(2024, 4, 1)))
        self.assertEqual(schedule(date(2024, 3, 29)), (False, None))

    def test_new_year_saturday_does_not_close_previous_friday(self):
        self.assertEqual(schedule(date(2021, 12, 31)), (True, date(2022, 1, 3)))


if __name__ == "__main__":
    unittest.main()
