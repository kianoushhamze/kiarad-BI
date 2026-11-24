"""Regression cases for real catalog identity, source grounding and safe tools."""
from copy import deepcopy
from datetime import date
import json
import unittest
from unittest.mock import MagicMock, patch

import assistant_engine as assistant
import assistant_reports as reports
from assistant_inventory import resolve_selection, inventory_answer, toman, business_date, dates_for_model, question_window, limit_short_window_orders, catalog_intent

PRODUCTS = [
    {'id':1,'code':'001','name':'LUFENTE کرم بدن','holoo_erp_code':'p1','stock':0,'price':1000},
    {'id':2,'code':'002','name':'LUFENTE اسپری بدن','holoo_erp_code':'p2','stock':0,'price':2000},
    {'id':3,'code':'003','name':'DERMALIST شامپو','holoo_erp_code':'p3','stock':99,'price':3000},
]


def analysis():
    common={'active':True,'stock':0,'reserved':0,'outbound_quantity':90,'return_quantity':2,'free_outbound_units':3,
            'net_sales_irr':10000,'stock_cover_days':0,'outbound_trend_percent':20,'policy':None,'order':{'status':'policy_required','suggested_quantity':None}}
    return {'status':'observed','source_fresh':True,'from_date':'2026-07-23','to_date':'2026-10-20','covered_days':90,'snapshot_id':12,
            'captured_at':'2026-10-20T10:00:00+00:00','items':[dict(common,erp_code='p1',name='LUFENTE کرم بدن',display_code='001'),dict(common,erp_code='p2',name='LUFENTE اسپری بدن',display_code='002',outbound_quantity=0,net_sales_irr=0)]}


class CatalogGroundingTests(unittest.TestCase):
    def test_real_large_currency_display_retains_digits_and_fraction(self):
        from decimal import Decimal
        source={'totals':{'net_sales_irr':Decimal('15840476455')},'cost_irr':None,'growth_percent':20,'rows':[{'refund_irr':Decimal('-15.25')}]}
        rendered=dates_for_model(source)
        self.assertEqual(rendered['totals']['net_sales_irr_toman_display'],'۱,۵۸۴,۰۴۷,۶۴۵.۵ تومان')
        self.assertEqual(rendered['rows'][0]['refund_irr_toman_display'],'-۱.۵۲۵ تومان')
        self.assertIn('نامعلوم',rendered['cost_irr_toman_display'])
        self.assertNotIn('growth_percent_toman_display',rendered)
        self.assertNotIn('net_sales_irr_toman_display',source['totals'])

    def test_persian_latin_and_known_typo_match_only_source_names(self):
        for q in ('برند لوفنته','از برند لوفتنه چی سفارش بدم؟','LUFENTE','موجودی محصولات لوفنته'):
            with self.subTest(q=q):
                selected=resolve_selection(q,PRODUCTS)
                self.assertEqual(selected['status'],'matched')
                self.assertEqual({r['id'] for r in selected['items']},{1,2})

    def test_alias_disabled_when_actual_catalog_prefix_absent(self):
        self.assertEqual(resolve_selection('برند لوفنته',PRODUCTS[2:])['status'],'not_found')

    def test_brand_plus_product_descriptor_preserves_sku_filter(self):
        result=resolve_selection('موجودی کرم لوفنته',PRODUCTS)
        self.assertEqual([r['id'] for r in result['items']],[1])

    def test_other_business_intents_are_not_hijacked_by_brand_names(self):
        for q in ('تارگت برند لوفنته یک میلیارد تومان بگذار','پورسانت فروش برند لوفنته چقدر است','سود خرید کالاها چقدر است','تولیدکننده برند لوفنته کیست'):
            self.assertFalse(catalog_intent(q))

    def test_other_brands_and_typo_candidates_work(self):
        self.assertEqual(resolve_selection('برند درمالیست',PRODUCTS)['items'][0]['id'],3)
        r=resolve_selection('برند درمالیس',PRODUCTS)
        self.assertEqual(r['status'],'not_found')
        self.assertIn('درمالیست',r['candidates'])

    def test_unknown_explicit_brand_never_reuses_previous_brand(self):
        r=resolve_selection('برند ناشناخته',PRODUCTS,['برند لوفنته'])
        self.assertEqual(r['status'],'not_found')

    def test_ambiguous_brand_never_picks_first(self):
        self.assertEqual(resolve_selection('لوفنته و درمالیست',PRODUCTS)['status'],'ambiguous')

    def test_followup_uses_adjacent_user_catalog_identity(self):
        r=resolve_selection('با توجه به موجودی انبارمون و کاردکس فروشش بهم بگو',PRODUCTS,['از برند لوفنته چی سفارش بدم؟'])
        self.assertEqual(r['status'],'matched')
        self.assertEqual(r['label'],'لوفنته')

    def test_new_topic_and_company_overview_do_not_inherit_brand(self):
        for q,history in [('وضعیت انبار چطور است',['برند لوفنته']),('کاردکس فروشش رو بگو',['برند لوفنته','حقوق نجمی چقدر است'])]:
            self.assertEqual(resolve_selection(q,PRODUCTS,history)['status'],'needs_selection')

    def test_sku_recommendations_do_not_invent_policy_or_buy_zero_demand(self):
        result=inventory_answer(resolve_selection('لوفنته',PRODUCTS),analysis(),'ceo')
        self.assertEqual(result['matched_count'],2)
        self.assertIn('خرید مجدد فعلاً توجیه فروش ندارد',result['answer'])
        self.assertIn('زمان تأمین',result['answer'])
        self.assertIn('۱,۰۰۰ تومان',result['answer'])
        self.assertNotIn('۱۰,۰۰۰ تومان',result['answer'])
        self.assertFalse(result['automatic_purchase'])
        self.assertTrue(all(r['order']['suggested_quantity'] is None for r in result['items']))

    def test_stale_partial_and_missing_mapping_block_purchase(self):
        for mode in ('stale','partial','mapping'):
            data=analysis()
            if mode=='stale':data['source_fresh']=False
            if mode=='partial':data['status']='partial'
            if mode=='mapping':data['items']=data['items'][:1]
            value=inventory_answer(resolve_selection('لوفنته',PRODUCTS),data,'ceo')
            self.assertNotIn('پیشنهاد قابل بازبینی',value['answer'])
            self.assertFalse(value['automatic_purchase'])

    def test_sales_manager_answer_has_no_sales_revenue(self):
        from field_intelligence import redact_inventory
        data=redact_inventory(analysis(),{'role':'sales_manager'})
        value=inventory_answer(resolve_selection('لوفنته',PRODUCTS),data,'sales_manager')
        self.assertNotIn('فروش خالص کالا:',value['answer'])
        self.assertTrue(all('net_sales_irr' not in r for r in value['items']))

    def test_unit_and_iran_date(self):
        self.assertEqual(toman(10000),'۱,۰۰۰ تومان')
        self.assertEqual(toman(None),'نامعلوم')
        self.assertIn('۱۴۰۵/۰۷/۲۸',business_date(date(2026,10,20)))
        self.assertIn('۱۳:۳۰',business_date('2026-10-20T10:00:00+00:00'))

    def test_current_price_uses_same_snapshot_and_currency_factor(self):
        from test_inventory_intelligence import payload,TODAY
        from inventory_intelligence import analyze_inventory
        source=payload();source['currency_factor']=10
        source['sources']['products']['rows'][0]['SellPrice']=12345
        result=analyze_inventory(source,TODAY)
        self.assertEqual(result['items'][0]['current_sell_price_irr'],123450)
        self.assertEqual(toman(result['items'][0]['current_sell_price_irr']),'۱۲,۳۴۵ تومان')

    def test_model_receives_computed_date_labels(self):
        value=dates_for_model({'from_date':'2026-10-01','rows':[{'time':'2026-10-20T10:00:00+00:00'}]})
        self.assertEqual(value['from_date_display'],'۱۴۰۵/۰۷/۰۹')
        self.assertIn('۱۳:۳۰',value['rows'][0]['time_display'])

    def test_question_window_honors_persian_digits_and_jalali_month(self):
        self.assertEqual(question_window('فروش ۷ روز اخیر',date(2026,10,20)),7)
        self.assertEqual(question_window('گردش ۳۰ روز',date(2026,10,20)),30)
        self.assertEqual(question_window('این ماه',date(2026,10,20)),28)

    def test_short_history_never_suggests_a_purchase_quantity(self):
        data=analysis()
        data['items'][0]['order']={'status':'review_order','suggested_quantity':100}
        data['requested_days']=7
        limited=limit_short_window_orders(data,7)
        self.assertIsNone(limited['items'][0]['order']['suggested_quantity'])
        self.assertIn('کوتاه است',inventory_answer(resolve_selection('لوفنته',PRODUCTS),limited,'ceo')['answer'])

    def test_database_date_keeps_date_and_failure_stays_unknown(self):
        conn=MagicMock();conn.execute.return_value.scalar.return_value=date(2026,10,20)
        self.assertEqual(assistant._safe_query(conn,'SELECT'), '2026-10-20')
        conn.execute.side_effect=RuntimeError()
        self.assertIsNone(assistant._safe_query(conn,'SELECT'))


class ReportToolSafetyTests(unittest.TestCase):
    def test_campaign_ai_receives_real_actor_and_rejects_invalid_model_amount(self):
        import campaign_ai
        from fastapi import HTTPException
        user={'id':1,'role':'ceo','salesperson_id':None}
        with patch.object(campaign_ai.engine,'connect'),patch.object(campaign_ai,'build_live_context',return_value={'sales_30d':10000,'invoices_30d':1}) as context,patch.object(campaign_ai,'build_market_brief',return_value=([],[],9000)),patch.object(campaign_ai,'get_connection') as write:
            for amount in (0,-1,999999,'NaN'):
                with patch.object(campaign_ai,'call_gpt',return_value=json.dumps({'title':'آزمایشی','target_amount':amount,'reward_value':0})) as model:
                    with self.assertRaises(HTTPException):
                        campaign_ai.suggest(user)
                    self.assertEqual(model.call_args.args[1]['_actor'],user)
            context.assert_called_with(context.call_args.args[0],user)
            write.assert_not_called()

    def test_campaign_ai_does_not_generate_target_from_missing_sales(self):
        import campaign_ai
        from fastapi import HTTPException
        with patch.object(campaign_ai.engine,'connect'),patch.object(campaign_ai,'build_live_context',return_value={'sales_30d':None,'invoices_30d':None}),patch.object(campaign_ai,'build_market_brief',return_value=([],[],0)),patch.object(campaign_ai,'call_gpt') as model:
            with self.assertRaises(HTTPException):
                campaign_ai.suggest({'id':1,'role':'ceo'})
            model.assert_not_called()
    def test_advisory_reuses_same_grounded_chat(self):
        with patch.object(assistant,'chat',return_value={'answer':'گزارش مستند','mode':'verified_catalog_analysis'}) as chat,patch.object(assistant,'_call_agent_with_tools') as legacy:
            result=assistant.advisory_ask(assistant.AdvisoryRequest(question='برند لوفنته'),{'id':1,'role':'ceo'})
            self.assertEqual(result['final'],'گزارش مستند')
            self.assertEqual(result['mode'],'verified_catalog_analysis')
            chat.assert_called_once()
            legacy.assert_not_called()

    def test_advisory_without_permission_does_not_read_or_call_model(self):
        from fastapi import HTTPException
        with patch.object(assistant,'role_has_module_permission',return_value=False),patch.object(assistant,'chat') as chat:
            with self.assertRaises(HTTPException):
                assistant.advisory_ask(assistant.AdvisoryRequest(question='گزارش شرکت'),{'id':2,'role':'visitor'})
            chat.assert_not_called()
    def test_target_form_rejects_invalid_amount_dates_and_person_before_write(self):
        from operations import create_person_target
        from fastapi import HTTPException
        valid={'title':'تارگت آزمایشی','target_amount':1000,'start_date':'2026-10-01','end_date':'2026-10-20'}
        with patch('operations.engine.begin') as begin:
            for invalid in ({'target_amount':'NaN'},{'target_amount':-1},{'start_date':'1405/13/01'},{'end_date':'2026-09-01'},{'salesperson_id':True},{'title':''}):
                with self.subTest(invalid=invalid),self.assertRaises(HTTPException) as error:
                    create_person_target({**valid,**invalid},{'role':'ceo','id':1})
                self.assertEqual(error.exception.status_code,422)
            begin.assert_not_called()

    def test_staff_cannot_choose_other_person_sales(self):
        with patch.object(reports,'role_has_module_permission',return_value=True),patch.object(reports.engine,'connect') as conn:
            value=reports.execute_report_tool('read_business_report',{'section':'sales','salesperson_id':99},{'id':2,'role':'visitor','salesperson_id':7})
            self.assertEqual(value['status'],'access_denied')
            conn.assert_not_called()
    def test_unknown_tool_and_extra_injection_arguments_denied(self):
        user={'id':1,'role':'ceo'}
        for name,args in [('sql',{'sql':'DELETE FROM sales'}),('read_business_report',{'section':'sales','role':'ceo'}),('read_business_report',{'section':'sales','days':9999})]:
            result=reports.execute_report_tool(name,args,user)
            self.assertIn(result['status'],('unknown_tool','invalid_arguments'))

    def test_staff_treasury_and_other_payroll_denied_before_source(self):
        with patch.object(reports,'role_has_module_permission',return_value=True),patch.object(reports.engine,'connect') as conn:
            for args in ({'section':'treasury'},{'section':'payroll','salesperson_id':8,'month':'1405-07'}):
                result=reports.execute_report_tool('read_business_report',args,{'id':9,'role':'visitor','salesperson_id':7})
                self.assertEqual(result['status'],'access_denied')
            conn.assert_not_called()

    def test_target_draft_requires_manager_and_explicit_fields(self):
        with patch.object(reports.engine,'connect') as conn:
            result=reports.execute_report_tool('prepare_target',{}, {'id':9,'role':'visitor'})
            self.assertEqual(result['status'],'access_denied')
            result=reports.execute_report_tool('prepare_target',{'scope':'company','amount':100}, {'id':1,'role':'ceo'})
            self.assertEqual(result['status'],'invalid_arguments')
            conn.assert_not_called()

    def test_target_draft_converts_units_and_does_not_write(self):
        with patch.object(reports.engine,'connect') as conn,patch.object(reports,'iran_month_bounds',return_value=(date(2026,9,23),date(2026,10,23))):
            result=reports.execute_report_tool('prepare_target',{'scope':'company','amount':1000000000,'unit':'toman','period':'current_jalali_month'}, {'id':1,'role':'ceo'})
            self.assertEqual(result['status'],'draft_only')
            self.assertEqual(result['draft']['target_amount'],'10000000000')
            self.assertEqual(result['draft']['end_date'],'2026-10-22')
            self.assertFalse(result['saved'])
            self.assertTrue(result['review_href'].startswith('/person-targets?assistant_draft='))
            conn.return_value.__enter__.return_value.execute.assert_not_called()

    def test_failed_report_is_not_empty_or_zero(self):
        with patch.object(reports,'read_report',side_effect=RuntimeError('private db detail')):
            value=reports.execute_report_tool('read_business_report',{'section':'sales'}, {'id':1,'role':'ceo'})
        self.assertEqual(value['status'],'source_error')
        self.assertNotIn('private',json.dumps(value))

    def test_actor_is_not_sent_to_model_and_tools_are_authorized_on_server(self):
        responses=[{'choices':[{'message':{'tool_calls':[{'id':'t1','type':'function','function':{'name':'read_business_report','arguments':'{"section":"sales"}'}}]}}]},
                   {'choices':[{'message':{'content':'نتیجهٔ گزارش مجاز'}}]}]
        response=MagicMock();response.status_code=200;response.json.side_effect=responses
        user={'id':88,'role':'visitor','salesperson_id':7}
        with patch.object(assistant,'get_env_live',return_value='setting'),patch.object(assistant.requests,'post',return_value=response) as request,patch.object(reports,'execute_report_tool',return_value={'status':'access_denied'}) as execute:
            result=assistant.call_gpt('فروش من',{'_actor':user,'scope':'personal'},[],'visitor','')
            self.assertEqual(result,'نتیجهٔ گزارش مجاز')
            self.assertEqual(execute.call_args.args[2],user)
            system=request.call_args.kwargs['json']['messages'][0]['content']
            self.assertNotIn('_actor',system)
            self.assertNotIn('88',system)

    def test_staff_target_intake_does_not_call_model(self):
        with patch.object(assistant,'load_history',return_value=[]),patch.object(assistant,'save_turn'),patch.object(assistant,'call_gpt') as model:
            value=assistant.chat(assistant.ChatRequest(message='تارگت رو بگم میتونی ست کنی؟'),{'id':1,'role':'visitor'})
            self.assertEqual(value['mode'],'access_limited')
            model.assert_not_called()

    def test_manager_target_intake_offers_draft_not_false_inability(self):
        with patch.object(assistant,'load_history',return_value=[]),patch.object(assistant,'save_turn'),patch.object(assistant,'call_gpt') as model:
            value=assistant.chat(assistant.ChatRequest(message='تارگت رو بگم میتونی ست کنی؟'),{'id':1,'role':'ceo'})
            self.assertEqual(value['mode'],'target_intake')
            self.assertIn('پیش‌نویس',value['answer'])
            self.assertIn('تأیید',value['answer'])
            model.assert_not_called()


if __name__=='__main__':
    unittest.main()
