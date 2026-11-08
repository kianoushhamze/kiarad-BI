from contextlib import nullcontext
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine, text
import base_registry as registry
import field_intelligence as intel


class RegistryPureTests(unittest.TestCase):
    def test_partial_words_and_persian_variants(self):
        self.assertTrue(registry.matches_search('رازي كرمان', 'داروخانه رازی', 'کرمان'))
        self.assertTrue(registry.matches_search('افتاب', 'ضد آفتاب'))
        self.assertFalse(registry.matches_search('رازی بم', 'رازی', 'کرمان'))

    def test_staff_cannot_import_or_preview(self):
        with patch.object(intel, 'engine') as engine:
            for call in (lambda:intel.holoo_bases_preview({'id':2,'role':'visitor'}),
                         lambda:intel.holoo_bases_import(intel.HolooBaseImport(snapshot_id=1,confirm_local_only=True),{'id':2,'role':'visitor'})):
                with self.assertRaises(HTTPException) as failure:call()
                self.assertEqual(failure.exception.status_code,403)
            engine.connect.assert_not_called();engine.begin.assert_not_called()


@unittest.skipUnless(os.getenv('KIARAD_TEST_BASE_REGISTRY_DB')=='1','Temporary database opt-in')
class RegistryDatabaseTests(unittest.TestCase):
    def setUp(self):
        import db
        self.engine=create_engine(db.engine.url,connect_args={'options':'-c search_path=pg_temp -c statement_timeout=15000 -c lock_timeout=3000','connect_timeout':5})
        self.addCleanup(self.engine.dispose)
        self.conn=self.engine.connect();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.assertEqual(self.conn.exec_driver_sql('SHOW search_path').scalar(),'pg_temp')
        statements=[
            'CREATE TEMP TABLE customers(id INT PRIMARY KEY,name TEXT,code TEXT,city TEXT,address TEXT,phone TEXT)',
            "INSERT INTO customers VALUES(1,'داروخانه آزمایشی','c1','کرمان',NULL,NULL),(2,'طرف حساب آزمایشی','c2',NULL,NULL,NULL)",
            'CREATE TEMP TABLE holoo_entity_mappings(entity_type TEXT,local_id INT,holoo_erp_code TEXT)',
            "INSERT INTO holoo_entity_mappings VALUES('customer',1,'c1'),('customer',2,'c2')",
            'CREATE TEMP TABLE holoo_financial_snapshots(id INT PRIMARY KEY,payload JSONB,captured_at TIMESTAMPTZ DEFAULT NOW())',
            'CREATE TEMP TABLE holoo_operational_runs(snapshot_id INT,receipt JSONB)',
            "INSERT INTO holoo_operational_runs VALUES(1,'{\"status\":\"completed\"}')",
            'CREATE TEMP TABLE base_coach_profiles(id SERIAL PRIMARY KEY,base_source TEXT,base_id INT,revision INT,payload JSONB,created_by INT)',
        ]
        for table in registry.BASES:
            statements.append(f'CREATE TEMP TABLE {table}(id SERIAL PRIMARY KEY,name TEXT,city TEXT,address TEXT,phone TEXT,type TEXT,latitude FLOAT,longitude FLOAT)')
        for statement in statements:self.conn.execute(text(statement))
        payload={'sources':{'customers':{'ok':True,'complete':True,'rows':[{'ErpCode':'c1'},{'ErpCode':'c2'}]}}}
        self.conn.execute(text('INSERT INTO holoo_financial_snapshots VALUES(1,CAST(:p AS JSONB),NOW())'),{'p':json.dumps(payload)})
        registry.ensure_registry(self.conn);registry.ensure_registry(self.conn)

    def count(self,table):return self.conn.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()

    def test_preview_never_creates_base(self):
        preview=registry.preview_import(self.conn)
        self.assertEqual(preview['new_bases'],2);self.assertEqual(preview['source_customers'],2)
        self.assertEqual(self.count('kerman_bases_manual'),0);self.assertEqual(self.count('holoo_customer_bases'),0)

    def test_import_is_idempotent_and_does_not_guess_fields(self):
        result=registry.import_customers(self.conn,1,1)
        self.assertEqual(result['created_bases'],2)
        self.assertEqual(registry.import_customers(self.conn,1,1)['created_bases'],0)
        self.assertEqual(self.count('kerman_bases_manual'),2);self.assertEqual(self.count('customers'),2)
        for row in self.conn.execute(text('SELECT type,latitude,longitude FROM kerman_bases_manual')).mappings():
            self.assertEqual(row['type'],'holoo_counterparty');self.assertIsNone(row['latitude']);self.assertIsNone(row['longitude'])
        profile=self.conn.execute(text('SELECT payload FROM base_coach_profiles LIMIT 1')).scalar()
        self.assertEqual(profile['grade'],'unknown');self.assertIsNone(profile['monthly_capacity'])

    def test_stale_preview_has_no_effect(self):
        with self.assertRaises(HTTPException):registry.import_customers(self.conn,2,1)
        self.assertEqual(self.count('kerman_bases_manual'),0)

    def test_missing_mapping_blocks_entire_import(self):
        self.conn.execute(text("DELETE FROM holoo_entity_mappings WHERE holoo_erp_code='c2'"))
        with self.assertRaises(HTTPException):registry.import_customers(self.conn,1,1)
        self.assertEqual(self.count('kerman_bases_manual'),0)

    def test_explicit_existing_profile_is_reused_not_name_matched(self):
        self.conn.execute(text("INSERT INTO pharmacies(id,name) VALUES(100,'نام متفاوت آزمایشی')"))
        self.conn.execute(text("INSERT INTO base_coach_profiles(base_source,base_id,revision,payload,created_by) VALUES('pharmacies',100,1,CAST(:payload AS JSONB),1)"),{'payload':json.dumps({'customer_id':1})})
        self.assertEqual(registry.preview_import(self.conn)['reuse_explicit_links'],1)
        result=registry.import_customers(self.conn,1,1)
        self.assertEqual(result['created_bases'],1);self.assertEqual(result['registered_links'],2)
        self.assertEqual(self.conn.execute(text('SELECT base_id FROM holoo_customer_bases WHERE customer_id=1')).scalar(),100)

    def test_imported_identity_cannot_be_relinked(self):
        registry.import_customers(self.conn,1,1)
        base_id=self.conn.execute(text('SELECT base_id FROM holoo_customer_bases WHERE customer_id=1')).scalar()
        with patch.object(intel,'engine',SimpleNamespace(begin=lambda:nullcontext(self.conn))):
            with self.assertRaises(HTTPException) as failure:
                intel.save_base_profile('kerman_bases_manual',base_id,intel.BaseProfile(customer_id=None,source_note='آزمون تغییر هویت واردشده',expected_revision=1),{'id':1,'role':'ceo'})
        self.assertEqual(failure.exception.status_code,409)
