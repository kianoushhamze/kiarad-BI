"""Synthetic panel regressions. All campaign writes use a mocked transaction."""
import inspect
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, Request
from assistant_inventory import resolve_selection
from product_pricing import selected_price
import campaign_ai
import crud_api


class PanelRepairTests(unittest.TestCase):
    def test_base_source_migration_preserves_unknown_provenance(self):
        conn = MagicMock()
        crud_api._ensure_base_source_columns(conn)
        statements = [str(call.args[0]) for call in conn.execute.call_args_list]
        self.assertEqual(statements, [
            'ALTER TABLE IF EXISTS pharmacies ADD COLUMN IF NOT EXISTS source TEXT',
            'ALTER TABLE IF EXISTS cosmetics_shops ADD COLUMN IF NOT EXISTS source TEXT',
        ])

    def test_private_catalog_files_require_account_and_cannot_traverse(self):
        dep=inspect.signature(crud_api.serve_file).parameters['user'].default
        self.assertIs(dep.dependency,crud_api.current_user)
        request = Request({'type':'http','headers':[]})
        for path in ('catalog/../temp/probe.pdf','products/images/../../temp/probe.pdf','temp/probe.pdf','catalog/..\\temp\\probe.pdf'):
            with self.subTest(path=path),self.assertRaises(HTTPException) as result:
                crud_api.serve_file(path,request,{'role':'ceo'})
            self.assertEqual(result.exception.status_code,403)
        scratch=Path(tempfile.gettempdir())
        with tempfile.TemporaryDirectory(dir=scratch) as folder,patch.object(crud_api,'UPLOAD_ROOT',Path(folder)):
            Path(folder).resolve().relative_to(scratch.resolve())
            target=Path(folder)/'catalog'/'probe.pdf';target.parent.mkdir();target.write_bytes(b'%PDF- synthetic')
            result=crud_api.serve_file('catalog/probe.pdf',request,{'role':'ceo'})
            self.assertEqual(result.headers['cache-control'],'private, no-cache')
            self.assertEqual(result.headers['vary'],'Authorization, Cookie')
            conditional = Request({'type':'http','headers':[(b'if-none-match', result.headers['etag'].encode())]})
            cached = crud_api.serve_file('catalog/probe.pdf',conditional,{'role':'ceo'})
            self.assertEqual(cached.status_code,304)
            self.assertEqual(cached.body,b'')
            self.assertEqual(result.headers['x-content-type-options'],'nosniff')
    def test_partial_product_keywords_and_conversation_words(self):
        rows=[{'id':1,'name':'کرم مرطوب کننده بدن آلوئه ورا ۲۰۰','code':'001'},
              {'id':2,'name':'ژل شستشوی صورت','code':'12'}]
        for question in ('قیمت کرم بدن رو بهم نشون میدی؟','موجودی مرطوب بدن بده'):
            with self.subTest(question=question):
                selection=resolve_selection(question,rows)
                self.assertEqual(selection['status'],'matched')
                self.assertEqual([row['id'] for row in selection['items']],[1])
        self.assertEqual(resolve_selection('قیمت کد 12',rows)['items'][0]['id'],2)
        self.assertEqual(resolve_selection('قیمت کرم ناشناخته',rows)['status'],'not_found')

    def test_price_levels_never_use_client_price_or_unknown_fallback(self):
        product={'price':100,'price2':80}
        self.assertEqual(selected_price(product,1),100)
        self.assertEqual(selected_price(product,2),80)
        for level in (False,True,1.0,0,3,'2',None):
            with self.subTest(level=level),self.assertRaises(HTTPException):selected_price(product,level)
        for value in (None,0,-1,'NaN','Infinity'):
            with self.subTest(value=value),self.assertRaises(HTTPException):selected_price({'price':100,'price2':value},2)

    def test_suggestion_storage_and_jsonb_payload(self):
        conn=MagicMock()
        campaign_ai.ensure_suggestion_storage(conn)
        statement=str(conn.execute.call_args.args[0])
        self.assertIn('CREATE TABLE IF NOT EXISTS ai_suggestions',statement)
        self.assertIn('payload JSONB NOT NULL',statement)
        self.assertEqual(campaign_ai.suggestion_payload({'title':'نمونه'}),{'title':'نمونه'})
        self.assertEqual(campaign_ai.suggestion_payload('{"title":"نمونه"}'),{'title':'نمونه'})
        self.assertEqual(campaign_ai.suggestion_payload('[1]'),{})

    def test_pending_is_manager_only(self):
        dep=inspect.signature(campaign_ai.pending).parameters['user'].default
        self.assertIs(dep.dependency,campaign_ai.require_manager)

    def campaign_fixture(self,status='pending'):
        conn=MagicMock();cur=conn.cursor.return_value.__enter__.return_value
        payload={'title':'کمپین آزمایشی','starts_at':'2026-10-20','ends_at':'2026-11-20',
                 'target_amount':10000,'reward_type':'percent','reward_value':2}
        cur.fetchone.side_effect=[(payload,status),(99,)]
        return conn,cur

    def test_approval_locks_before_insert_and_closes(self):
        conn,cur=self.campaign_fixture()
        with patch('campaign_ai.get_connection',return_value=conn):
            result=campaign_ai.decide({'suggestion_id':8,'action':'approve'},{'id':1,'role':'ceo'})
        self.assertEqual(result,{'status':'approved','campaign_id':99})
        self.assertIn('FOR UPDATE',cur.execute.call_args_list[0].args[0])
        self.assertEqual(sum('INSERT INTO campaigns' in call.args[0] for call in cur.execute.call_args_list),1)
        conn.close.assert_called_once()

    def test_repeated_approval_never_inserts(self):
        conn,cur=self.campaign_fixture('approved')
        with patch('campaign_ai.get_connection',return_value=conn),self.assertRaises(HTTPException) as result:
            campaign_ai.decide({'suggestion_id':8,'action':'approve'},{'id':1,'role':'ceo'})
        self.assertEqual(result.exception.status_code,409)
        self.assertEqual(cur.execute.call_count,1)
        conn.close.assert_called_once()

    def test_invalid_identifiers_fail_before_connection(self):
        for value in (True,'wrong',1.1,0,None):
            with self.subTest(value=value),patch('campaign_ai.get_connection') as connection,self.assertRaises(HTTPException):
                campaign_ai.decide({'suggestion_id':value,'action':'approve'},{'id':1,'role':'ceo'})
            connection.assert_not_called()
