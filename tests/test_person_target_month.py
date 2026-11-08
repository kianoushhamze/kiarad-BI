from datetime import date
import unittest
from unittest.mock import MagicMock, patch
from iran_time import iran_month_bounds
from operations import my_target_summary


class PersonalMonthTests(unittest.TestCase):
    def test_summary_uses_shamsi_bounds_instead_of_gregorian_month(self):
        start,end=iran_month_bounds(date(2026,11,2))
        self.assertEqual((start,end),(date(2026,10,23),date(2026,11,22)))
        conn=MagicMock()
        conn.execute.return_value.mappings.return_value.all.return_value=[]
        conn.execute.return_value.scalar.return_value=0
        with patch('operations.engine.connect') as connect, patch('operations.iran_month_bounds',return_value=(start,end)):
            connect.return_value.__enter__.return_value=conn
            my_target_summary({'salesperson_id':7})
        call=conn.execute.call_args_list[1]
        self.assertEqual(call.args[1],{'spid':7,'month_start':start,'month_end':end})
        self.assertNotIn('DATE_TRUNC',str(call.args[0]))
