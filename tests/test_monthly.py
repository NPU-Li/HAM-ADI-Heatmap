import unittest
from datetime import date, timedelta
from plot_qso import aggregate_monthly


class MonthlyTests(unittest.TestCase):
    def test_latest_day_window_and_band_filter(self):
        end = date(2026, 10, 29)
        start = end - timedelta(days=364)
        rows = [(start - timedelta(days=1), {'BAND': '20M'}),
                (start, {'BAND': '20M'}), (end, {'BAND': '40m'}),
                (end, {'BAND': '2M'})]
        first, last, counts, excluded = aggregate_monthly(rows)
        self.assertEqual((first, last), (start, end))
        self.assertEqual(sum(sum(c.values()) for c in counts.values()), 2)
        self.assertEqual(counts['2026-10']['40M'], 1)
        self.assertEqual(excluded['2M'], 1)
        self.assertEqual(len(counts), 13)

    def test_current_week_updates_month(self):
        rows = [(date(2026, 10, 25), {'BAND': '20M'})]
        rows.append((date(2026, 10, 29), {'BAND': '20M'}))
        _, end, counts, _ = aggregate_monthly(rows)
        self.assertEqual(end, date(2026, 10, 29))
        self.assertEqual(counts['2026-10']['20M'], 2)
