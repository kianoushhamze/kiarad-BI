from copy import deepcopy
from datetime import date
import unittest
from inventory_intelligence import analyze_inventory,order_scenario
from purchase_profit import estimate_purchase_profit

TODAY=date(2026,10,20)
def invoice(key,day,qty,price,product='p1'):
    return {'ErpCode':key,'Date':day,'SumPrice':qty*price,'SumDiscount':0,'SumLevy':0,'SumScot':0,'Detail':[{'ProductErpCode':product,'Few':qty,'Price':price,'SumPrice':qty*price,'Discount':0,'PersentDiscount':0}]}
def payload():
    return {'currency_factor':1,'from_date':'2026-03-21','to_date':TODAY.isoformat(),'sources':{
        'products':{'ok':True,'complete':True,'rows':[{'ErpCode':'p1','Code':'001','Name':'آزمایشی','Few':10,'BuyPrice':50,'IsActive':True}]},
        'sales':{'ok':True,'complete':True,'rows':[invoice('s','2026-10-19',90,100)]},
        'purchases':{'ok':True,'complete':True,'rows':[invoice('p','2026-03-22',500,50)]},
        'sales_returns':{'ok':True,'complete':True,'rows':[]},'purchase_returns':{'ok':True,'complete':True,'rows':[]}}}
POLICY={'lead_days':10,'review_days':20,'safety_units':5,'minimum_order':10,'pack_units':6,'units_confirmed':True,'revision':1}
class InventoryIntelligenceTests(unittest.TestCase):
    def analyze(self,p=None,**kw):return analyze_inventory(p or payload(),TODAY,policies={'p1':POLICY},reservations={'p1':0},**kw)
    def test_explicit_reorder_formula_rounds_pack_and_minimum(self):
        r=order_scenario(10,0,1,POLICY)
        self.assertEqual(r['reorder_point'],15)
        self.assertEqual(r['target_stock'],35)
        self.assertEqual(r['suggested_quantity'],30)
        self.assertFalse(r['automatic_purchase'])
    def test_no_order_above_point_or_without_demand(self):
        self.assertEqual(order_scenario(20,0,1,POLICY)['suggested_quantity'],0)
        self.assertEqual(order_scenario(0,0,0,POLICY)['suggested_quantity'],0)
    def test_no_policy_and_unconfirmed_units_stay_unknown(self):
        for policy in (None,{**POLICY,'units_confirmed':False},{**POLICY,'pack_units':0}):
            self.assertIsNone(order_scenario(0,0,1,policy)['suggested_quantity'])
    def test_inactive_product_and_invalid_reserve_cannot_create_order(self):
        p=payload();p['sources']['products']['rows'][0]['IsActive']=False
        self.assertIsNone(self.analyze(p)['items'][0]['order']['suggested_quantity'])
        result=analyze_inventory(payload(),TODAY,policies={'p1':POLICY},reservations={'p1':'NaN'})
        self.assertIsNone(result['items'][0]['reserved'])
    def test_outbound_includes_free_units_and_returns_are_separate(self):
        p=payload();p['sources']['sales']['rows'].append(invoice('gift','2026-10-19',5,0))
        p['sources']['sales_returns']['rows'].append(invoice('return','2026-10-20',2,100))
        row=self.analyze(p)['items'][0]
        self.assertEqual(row['outbound_quantity'],95)
        self.assertEqual(row['return_quantity'],2)
        self.assertEqual(row['free_outbound_units'],5)
        self.assertEqual(row['net_sales_irr'],8800)
    def test_cost_reference_and_profit_are_not_sales_price_value(self):
        row=self.analyze()['items'][0]
        self.assertEqual(row['capital_at_current_purchase_price_irr'],500)
        self.assertEqual(row['estimated_gross_profit_irr'],4500)
    def test_missing_historical_purchase_does_not_create_profit(self):
        p=payload();p['sources']['purchases']['rows']=[]
        row=self.analyze(p)['items'][0]
        self.assertIsNone(row['estimated_gross_profit_irr'])
        self.assertEqual(row['net_sales_irr'],9000)
    def test_stale_source_partial_history_and_unknown_reservations_block_order(self):
        p=payload();p['to_date']='2026-10-19'
        self.assertIsNone(self.analyze(p)['items'][0]['order']['suggested_quantity'])
        p=payload();p['from_date']='2026-10-01'
        self.assertIsNone(self.analyze(p)['items'][0]['order']['suggested_quantity'])
        self.assertIsNone(analyze_inventory(payload(),TODAY,policies={'p1':POLICY})['items'][0]['order']['suggested_quantity'])
    def test_expired_or_overcounted_batches_block_order(self):
        for batch in ({'batch_code':'a','expiry_date':'2026-10-19','quantity':1},{'batch_code':'a','expiry_date':'2026-12-01','quantity':11}):
            self.assertIsNone(self.analyze(batches={'p1':[batch]})['items'][0]['order']['suggested_quantity'])
    def test_incomplete_duplicate_or_invalid_invoice_never_becomes_zero_demand(self):
        for mode in ('partial','duplicate','invalid'):
            p=payload()
            if mode=='partial':p['sources']['sales']['complete']=False
            elif mode=='duplicate':p['sources']['sales']['rows']*=2
            else:p['sources']['sales']['rows'][0]['Detail'][0]['Few']='NaN'
            row=self.analyze(p)['items'][0]
            self.assertIsNone(row['outbound_quantity'])
            self.assertIsNone(row['order']['suggested_quantity'])
    def test_no_sales_in_window_does_not_prove_stock_age(self):
        p=payload();p['sources']['sales']['rows']=[]
        row=self.analyze(p)['items'][0]
        self.assertIsNone(row['days_since_last_sale'])
        self.assertEqual(row['movement'],'بدون خروج در بازه')
        self.assertIsNone(row['stock_cover_days'])
    def test_largest_revenue_class_is_a(self):
        self.assertEqual(self.analyze()['items'][0]['abc_class'],'A')
    def test_input_unchanged_and_no_source_is_not_healthy(self):
        p=payload();before=deepcopy(p);self.analyze(p)
        self.assertEqual(p,before)
        self.assertEqual(analyze_inventory(None,TODAY)['status'],'source_missing')
    def test_per_product_window_keeps_purchase_history_but_filters_revenue(self):
        p=payload();p['sources']['sales']['rows'].insert(0,invoice('old','2026-04-01',1,100))
        result=estimate_purchase_profit({**p,'invoice_amount_semantics':{k:{'header_sum_price':'gross_before_discount_tax','header_discount_scope':'includes_line_discounts'} for k in ('sales','purchases','sales_returns','purchase_returns')}},0,detail_from='2026-10-01')
        self.assertEqual(result['products'][0]['net_sales_irr'],9000)
        self.assertEqual(result['products'][0]['estimated_cogs_irr'],4500)
