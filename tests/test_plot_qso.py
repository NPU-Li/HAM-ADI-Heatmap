import unittest
from datetime import date, timedelta

from plot_qso import aggregate, dated_records, parse_adif


class ADIFTests(unittest.TestCase):
    def test_lengths_header_and_comments(self):
        text = 'Report <PROGRAMID:4>LoTW<eoh><comment:5><eor><call:3>A1B\n<QSO_DATE:8>20261027 // comment\n<eor>'
        self.assertEqual(parse_adif(text), [{'COMMENT': '<eor>', 'CALL': 'A1B', 'QSO_DATE': '20261027'}])

    def test_bad_records(self):
        for text in ['<CALL:5>ABC', '<CALL:3>ABC', '<CALL:x>ABC<eor>']:
            with self.assertRaises(ValueError):
                parse_adif(text)
        with self.assertRaises(ValueError):
            dated_records([{'QSO_DATE': '20260230'}])

    def test_window_and_bands(self):
        end = date(2026, 10, 27)
        start = end - timedelta(days=364)
        rows = [(start - timedelta(days=1), {'BAND': '20M'}),
                (start, {'BAND': '20M'}), (end - timedelta(days=2), {'BAND': '40m'}),
                (end - timedelta(days=2), {'BAND': '2M'}), (end + timedelta(days=1), {'BAND': '10M'})]
        days, daily, weekly, excluded = aggregate(rows, end)
        self.assertEqual(len(days), 365)
        self.assertEqual(sum(daily.values()), 3)
        self.assertEqual(sum(sum(v.values()) for v in weekly.values()), 1)
        self.assertEqual(excluded, {'2M': 1})
        self.assertEqual(len(weekly), 12)

    def test_week_boundaries(self):
        end = date(2026, 10, 27)
        week_end = date(2026, 10, 25)
        start = week_end - timedelta(days=83)
        rows = [(start + timedelta(days=i), {'BAND': '20M'}) for i in range(-1, 85)]
        _, _, weekly, _ = aggregate(rows, end)
        self.assertEqual([sum(c.values()) for c in weekly.values()], [7] * 12)
        self.assertEqual(min(weekly), start)
        self.assertEqual(max(weekly) + timedelta(days=6), week_end)
        self.assertTrue(all(w.weekday() == 0 for w in weekly))

    def test_current_week_excluded_and_iso_year(self):
        for offset in range(7):
            anchor = date(2027, 1, 4) + timedelta(days=offset)
            _, _, weekly, _ = aggregate([(anchor, {'BAND': '20M'})], anchor)
            self.assertEqual(max(weekly), date(2026, 12, 28))
            self.assertEqual(max(weekly).isocalendar()[:2], (2026, 53))
            self.assertEqual(sum(sum(v.values()) for v in weekly.values()), 0)


if __name__ == '__main__':
    unittest.main()
