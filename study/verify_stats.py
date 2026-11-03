"""Calendar and aggregation regression checks for local study reports."""
from datetime import date
import unittest

from stats_core import build_report, move_period, period_bounds

CATEGORIES = [dict(id=1,title='A',color='#F4CF70'),dict(id=2,title='B',color='#97CFA8')]


class ReportsTests(unittest.TestCase):
    def test_calendar_week_and_year_boundary(self):
        self.assertEqual(period_bounds('week',date(2026,1,1)),(date(2025,12,29),date(2026,1,4)))
        self.assertEqual(len(build_report({},CATEGORIES,'week',date(2026,1,1)).days),7)

    def test_month_and_leap_year(self):
        self.assertEqual(period_bounds('month',date(2024,2,10)),(date(2024,2,1),date(2024,2,29)))
        self.assertEqual(move_period('month',date(2026,1,31),1),date(2026,2,28))
        self.assertEqual(move_period('month',date(2026,1,3),-1),date(2025,12,3))

    def test_totals_and_days_without_entries(self):
        totals = {(1,'2026-11-02'):3600,(2,'2026-11-02'):1800,(2,'2026-11-04'):7200,
                  (1,'2026-10-31'):555,(1,'2026-11-09'):123}
        report = build_report(totals,CATEGORIES,'week',date(2026,11,3))
        self.assertEqual(report.total,12600)
        self.assertEqual(report.category_totals,{1:3600,2:9000})
        self.assertEqual(report.daily_totals[date(2026,11,3)],0)
        self.assertEqual(report.active_days,2)
        self.assertEqual(report.average_active_day,6300)
        self.assertEqual(report.best_day,date(2026,11,4))
        self.assertEqual(report.first_recorded_day,date(2026,10,31))
        self.assertEqual(report.categories[0]['id'],2)
        self.assertEqual(totals[(1,'2026-10-31')],555)

    def test_day_distribution_matches_total(self):
        report = build_report({(1,'2026-11-03'):70.5,(2,'2026-11-03'):29.5},CATEGORIES,'day',date(2026,11,3))
        self.assertEqual(report.total,100)
        self.assertAlmostEqual(sum(report.category_totals.values())/report.total,1)

    def test_empty_and_future_periods(self):
        report = build_report({(1,'2026-11-03'):10},CATEGORIES,'month',date(2027,1,2))
        self.assertEqual(len(report.days),31)
        self.assertEqual(report.total,0)
        self.assertEqual(report.active_days,0)
        self.assertEqual(report.average_active_day,0)
        self.assertIsNone(report.best_day)


if __name__=='__main__':
    unittest.main(verbosity=2)
