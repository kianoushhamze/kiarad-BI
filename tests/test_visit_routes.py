"""Access-scope checks for visit routes; no real database rows are changed."""
import unittest
from unittest.mock import patch

import compensation


class FakeCursor:
    description = [("id",)]

    def __init__(self):
        self.params = None

    def execute(self, _query, params=None):
        self.params = params

    def fetchall(self):
        return []

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def close(self):
        pass


class VisitRouteScopeTests(unittest.TestCase):
    def test_staff_cannot_read_another_users_route(self):
        cursor = FakeCursor()
        with patch.object(compensation, "get_connection", return_value=FakeConnection(cursor)):
            compensation.list_visit_routes(user_id=99, user={"id": 4, "role": "visitor"})
        self.assertEqual(cursor.params, (4,))

    def test_manager_can_select_a_users_route(self):
        cursor = FakeCursor()
        with patch.object(compensation, "get_connection", return_value=FakeConnection(cursor)):
            compensation.list_visit_routes(user_id=99, user={"id": 1, "role": "ceo"})
        self.assertEqual(cursor.params, (99,))


if __name__ == "__main__":
    unittest.main()
