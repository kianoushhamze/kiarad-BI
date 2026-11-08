import unittest
from datetime import date, time
from fastapi import HTTPException
from monthly_visit_plans import Stop, ceo, haversine_m, month_window, schedule_guard, Draft, Workday
from pydantic import ValidationError


def stop(day, order, start=None, end=None, base=1):
    return Stop(visit_date=day, base_source='kerman_bases_manual', base_id=base, stop_order=order,
                objective='ویزیت تستی برنامه', start_time=start, end_time=end)


class MonthlyPlanGuards(unittest.TestCase):
    def test_jalali_month_boundaries(self):
        start,end=month_window('1405-12')
        self.assertLess(start,end)
        self.assertIn((end-start).days,(29,30))

    def test_invalid_month_rejected(self):
        for value in ('2026-11','1405-13','../users','1405-00'):
            with self.subTest(value=value),self.assertRaises(HTTPException):month_window(value)

    def test_only_ceo_can_approve(self):
        for role in ('visitor','salesperson','sales_manager','finance'):
            with self.subTest(role=role),self.assertRaises(HTTPException):ceo({'id':1,'role':role})

    def test_workday_bounds_and_extra_fields(self):
        for value in (-1,1.001,float('nan')):
            with self.assertRaises(ValidationError):Workday(work_date='2026-11-01',credited_days=value,note='توضیح مستند آزمون')
        with self.assertRaises(ValidationError):Draft(user_id=1,month='1405-09',stops=[],approved=True)


class RouteScheduleGuards(unittest.TestCase):
    day = date(2026, 11, 10)

    def test_timed_day_with_ordered_windows_is_accepted(self):
        schedule_guard([stop(self.day, 1, time(9), time(10)), stop(self.day, 2, time(10, 30), time(11, 30))])

    def test_untimed_day_is_still_accepted(self):
        schedule_guard([stop(self.day, 1), stop(self.day, 2)])

    def test_half_timed_day_is_rejected(self):
        with self.assertRaises(HTTPException):
            schedule_guard([stop(self.day, 1, time(9), time(10)), stop(self.day, 2)])

    def test_end_before_start_is_rejected(self):
        for start, end in ((time(10), time(10)), (time(11), time(9))):
            with self.subTest(start=start, end=end), self.assertRaises(HTTPException):
                schedule_guard([stop(self.day, 1, start, end)])

    def test_overlapping_windows_are_rejected(self):
        with self.assertRaises(HTTPException):
            schedule_guard([stop(self.day, 1, time(9), time(11)), stop(self.day, 2, time(10), time(12))])

    def test_same_day_is_capped(self):
        stops = [stop(self.day, index + 1) for index in range(12)]
        schedule_guard(stops)
        with self.assertRaises(HTTPException):
            schedule_guard(stops + [stop(self.day, 13, base=99)])

    def test_time_fields_cannot_be_invented(self):
        with self.assertRaises(ValidationError):
            Stop(visit_date=self.day, base_source='kerman_bases_manual', base_id=1, stop_order=1,
                 objective='ویزیت تستی برنامه', start_time='25:00')


class RouteDistance(unittest.TestCase):
    def test_one_degree_of_latitude_is_about_111_km(self):
        self.assertAlmostEqual(haversine_m((30.0, 57.0), (31.0, 57.0)) / 1000, 111.2, delta=0.5)

    def test_identical_points_are_zero(self):
        self.assertEqual(haversine_m((30.0, 57.0), (30.0, 57.0)), 0.0)

