"""آزمون شیفت با جدول‌های موقت؛ هیچ مختصاتی در داده‌های واقعی ثبت نمی‌شود."""
import math
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import compensation
from db import get_connection
from payroll_periods import current_payroll_month


class PositionValidationTests(unittest.TestCase):
    def test_invalid_and_nonfinite_positions_are_rejected_before_database_access(self):
        user = {"id": 2, "role": "salesperson", "salesperson_id": 10}
        for changes in ({"lat": None}, {"lat": True}, {"lat": "NaN"}, {"lng": "Infinity"},
                        {"lat": 91}, {"lng": -181}, {"accuracy_m": 0}, {"accuracy_m": -1},
                        {"accuracy_m": True}, {"accuracy_m": "NaN"}):
            data = {"salesperson_id": 10, "lat": 30, "lng": 57, "accuracy_m": 20}
            data.update(changes)
            for method in (compensation.start_attendance, compensation.stop_attendance):
                with self.subTest(changes=changes, method=method.__name__), patch.object(compensation, "get_connection") as connect:
                    with self.assertRaises(HTTPException) as error:
                        method(data, user)
                    self.assertEqual(error.exception.status_code, 422)
                    connect.assert_not_called()

    def test_other_profile_is_denied_before_database_access(self):
        user = {"id": 2, "role": "visitor", "salesperson_id": 10}
        with patch.object(compensation, "get_connection") as connect:
            for method in (compensation.start_attendance, compensation.stop_attendance):
                with self.assertRaises(HTTPException) as error:
                    method({"salesperson_id": 11, "lat": 30, "lng": 57}, user)
                self.assertEqual(error.exception.status_code, 403)
            with self.assertRaises(HTTPException) as error:
                compensation.attendance_status(salesperson_id=11, user=user)
            self.assertEqual(error.exception.status_code, 403)
            connect.assert_not_called()

    def test_extreme_valid_distance_stays_finite(self):
        self.assertTrue(math.isfinite(compensation.distance_m(-90, -180, 90, 180)))


class BorrowedConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return self.connection.cursor()

    def commit(self):
        pass

    def close(self):
        pass


@unittest.skipUnless(os.getenv("KIARAD_TEST_ATTENDANCE_DB") == "1", "آزمون موقت پایگاه‌داده نیازمند فعال‌سازی است")
class AttendanceTemporaryDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.conn = get_connection()
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.cur = self.conn.cursor()
        self.addCleanup(self.cur.close)
        self.cur.execute("CREATE TEMP TABLE salespersons (id INTEGER PRIMARY KEY)")
        self.cur.execute("INSERT INTO salespersons VALUES (10),(11)")
        self.cur.execute("CREATE TEMP TABLE payroll_approvals (salesperson_id INTEGER,payroll_month TEXT,status TEXT)")
        compensation._ensure_attendance_schema(self.cur, temporary=True)
        compensation._ensure_attendance_schema(self.cur, temporary=True)
        patcher = patch.object(compensation, "get_connection", return_value=BorrowedConnection(self.conn))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = {"id": 2, "role": "salesperson", "salesperson_id": 10}
        self.position = {"salesperson_id": 10, "lat": 30, "lng": 57, "accuracy_m": 20}

    def test_start_reload_repeated_start_and_stop_preserve_one_session(self):
        self.assertFalse(compensation.attendance_status(user=self.user)["is_active"])
        first = compensation.start_attendance(self.position, self.user)
        self.assertEqual(first["status"], "started")
        self.assertTrue(first["started_at"].endswith("+03:30"))
        reloaded = compensation.attendance_status(user=self.user)
        self.assertEqual(reloaded["session_id"], first["session_id"])
        self.assertTrue(reloaded["is_active"])
        again = compensation.start_attendance(self.position, self.user)
        self.assertEqual((again["status"], again["session_id"]), ("already_active", first["session_id"]))
        self.cur.execute("SELECT COUNT(*) FROM attendance_sessions")
        self.assertEqual(self.cur.fetchone()[0], 1)
        self.cur.execute("SELECT COUNT(*) FROM salesperson_locations")
        self.assertEqual(self.cur.fetchone()[0], 1)
        self.cur.execute("UPDATE attendance_sessions SET start_time=(NOW() AT TIME ZONE 'Asia/Tehran')-INTERVAL '2 hours'")
        stopped = compensation.stop_attendance(self.position, self.user)
        self.assertEqual(stopped["duration_hours"], 2)
        self.assertFalse(stopped["is_active"])
        self.assertFalse(compensation.attendance_status(user=self.user)["is_active"])
        self.cur.execute("SELECT activity,battery_level FROM salesperson_locations ORDER BY id")
        self.assertEqual(self.cur.fetchall(), [("shift_start", None), ("shift_end", None)])

    def test_stop_without_open_shift_and_duplicate_legacy_shifts_are_not_silently_changed(self):
        with self.assertRaises(HTTPException) as error:
            compensation.stop_attendance(self.position, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.cur.execute("INSERT INTO attendance_sessions (salesperson_id) VALUES (10),(10)")
        for call in (lambda: compensation.attendance_status(user=self.user),
                     lambda: compensation.start_attendance(self.position, self.user),
                     lambda: compensation.stop_attendance(self.position, self.user)):
            with self.assertRaises(HTTPException) as error:
                call()
            self.assertEqual(error.exception.status_code, 409)
        self.cur.execute("SELECT COUNT(*) FROM attendance_sessions WHERE is_active")
        self.assertEqual(self.cur.fetchone()[0], 2)
        self.cur.execute("SELECT COUNT(*) FROM salesperson_locations")
        self.assertEqual(self.cur.fetchone()[0], 0)

    def test_approved_persian_period_prevents_new_shift_without_writes(self):
        self.cur.execute("INSERT INTO payroll_approvals VALUES (%s,%s,'approved')", (10, current_payroll_month()))
        with self.assertRaises(HTTPException) as error:
            compensation.start_attendance(self.position, self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.cur.execute("SELECT COUNT(*) FROM attendance_sessions")
        self.assertEqual(self.cur.fetchone()[0], 0)
        self.cur.execute("SELECT COUNT(*) FROM salesperson_locations")
        self.assertEqual(self.cur.fetchone()[0], 0)

    def test_unknown_profile_does_not_create_location_or_session(self):
        with self.assertRaises(HTTPException) as error:
            compensation.start_attendance({**self.position, "salesperson_id": 999}, {"id": 1, "role": "ceo"})
        self.assertEqual(error.exception.status_code, 404)
        self.cur.execute("SELECT COUNT(*) FROM attendance_sessions")
        self.assertEqual(self.cur.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
