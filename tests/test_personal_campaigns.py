import unittest
from unittest.mock import MagicMock, patch
from operations import personal_campaigns


class PersonalCampaignTests(unittest.TestCase):
    def test_scope_is_enforced_for_staff(self):
        with patch("operations.engine.connect") as connect:
            conn = connect.return_value.__enter__.return_value
            conn.execute.return_value.mappings.return_value.all.return_value = []
            personal_campaigns(user_id=99, user={"id": 4, "role": "visitor"})
            self.assertEqual(conn.execute.call_args.args[1]["user_id"], 4)

    def test_manager_can_select_person(self):
        with patch("operations.engine.connect") as connect:
            conn = connect.return_value.__enter__.return_value
            conn.execute.return_value.mappings.return_value.all.return_value = []
            personal_campaigns(user_id=99, user={"id": 1, "role": "ceo"})
            self.assertEqual(conn.execute.call_args.args[1]["user_id"], 99)
