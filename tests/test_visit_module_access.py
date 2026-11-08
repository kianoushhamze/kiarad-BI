"""Regression checks for the module gate used by mobile visit endpoints."""
import unittest
from unittest.mock import patch

from api import _required_module
from operations import role_has_module_permission


class VisitModuleAccessTests(unittest.TestCase):
    def test_mobile_routes_use_modules_granted_to_field_staff_and_managers(self):
        expected={"/api/compensation/visit-routes":"tasks",
                  "/api/compensation/visit-coverage":"tasks",
                  "/api/compensation/base-portfolios":"kerman-bases",
                  "/api/compensation/base-proposals":"kerman-bases",
                  "/api/compensation/base-checkins":"kerman-bases",
                  "/api/compensation/base-checkins/12/review":"kerman-bases",
                  "/api/compensation/bases/pharmacies/1/location":"kerman-bases"}
        with patch("operations.engine.connect") as connect:
            connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all.return_value=[]
            for path,module in expected.items():
                self.assertEqual(_required_module(path),module)
                for role in ("salesperson","visitor","sales_manager"):
                    self.assertTrue(role_has_module_permission(role,module), (role,path))

    def test_configured_permissions_are_preserved(self):
        with patch("operations.engine.connect") as connect:
            connect.return_value.__enter__.return_value.execute.return_value.mappings.return_value.all.return_value=[
                {"module":"tasks","can_read":True,"can_write":True,"can_delete":False}]
            self.assertFalse(role_has_module_permission("sales_manager","kerman-bases"))


if __name__ == "__main__":
    unittest.main()
