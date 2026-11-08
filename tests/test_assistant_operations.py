import unittest
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError
import assistant_operations as actions


class OperationGuards(unittest.TestCase):
    def test_arbitrary_operation_is_rejected(self):
        with self.assertRaises(ValidationError):
            actions.OperationArgs(operation='execute_sql',payload={})

    def test_confirmation_must_be_explicit(self):
        with self.assertRaises(ValidationError):
            actions.Confirmation(confirm=False)

    def test_staff_cannot_assign_tasks(self):
        with patch.object(actions,'role_has_module_permission',return_value=True):
            with self.assertRaises(HTTPException) as denied:
                actions.authorize('create_task',{'id':2,'role':'salesperson'})
            self.assertEqual(denied.exception.status_code,403)

    def test_revoked_module_permission_is_respected(self):
        with patch.object(actions,'role_has_module_permission',return_value=False):
            with self.assertRaises(HTTPException):
                actions.authorize('create_daily_report',{'id':2,'role':'salesperson'})

    def test_unknown_task_fields_rejected_before_database(self):
        with patch.object(actions.engine,'begin') as database:
            with self.assertRaises(HTTPException):
                actions.prepare({'operation':'create_task','payload':{'title':'آزمون','assigned_to':1,'role':'ceo'}},{'id':1,'role':'ceo'})
            database.assert_not_called()
