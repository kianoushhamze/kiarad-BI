import unittest
from decimal import Decimal
from assistant_money import explicit_money,check_proposed_money


class MoneyGuards(unittest.TestCase):
    def test_spoken_and_numeric_amounts(self):
        self.assertEqual(explicit_money('۲۰ میلیون تومان و پانزده میلیون تومن و ۱٬۰۰۰ ریال'),[Decimal(200000000),Decimal(150000000),Decimal(1000)])

    def test_double_conversion_is_rejected(self):
        body={'body':{'unit':'TOMAN','rows':[{'target_amount':200000000}]}}
        self.assertEqual(check_proposed_money('هدف ۲۰ میلیون تومان','enter_targets',body)['status'],'needs_currency_review')
        body['body']['rows'][0]['target_amount']=20000000
        self.assertIsNone(check_proposed_money('هدف ۲۰ میلیون تومان','enter_targets',body))

    def test_already_converted_rial_is_accepted(self):
        self.assertIsNone(check_proposed_money('قیمت ۲ میلیون تومان','catalog_update_product',{'body':{'price':20000000}}))
