import os
import json
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import create_engine, text
import base_readiness as readiness
import field_intelligence as intel


class ReadinessPureTests(unittest.TestCase):
    def test_unreliable_coordinates_and_capacity_are_gaps(self):
        for lat,lon in [(None,57),('NaN',57),(30,'Infinity'),(91,57),(30,181)]:
            self.assertFalse(readiness.valid_location(lat,lon))
        self.assertTrue(readiness.valid_location('30.2','57.1'))
        for value in (None,'NaN','Infinity',0,-1,'bad'):
            self.assertFalse(readiness.positive_capacity(value))
        self.assertTrue(readiness.positive_capacity('0.01'))

    def test_staff_and_non_coach_roles_cannot_read_whole_registry(self):
        with patch.object(intel,'engine') as engine:
            for role in ('visitor','salesperson','finance','hr'):
                with self.assertRaises(HTTPException) as error:
                    intel.base_readiness({'id':2,'role':role})
                self.assertEqual(error.exception.status_code,403)
            engine.begin.assert_not_called()

    def test_empty_report_does_not_claim_province_coverage(self):
        report=readiness.summarize([])
        self.assertEqual(report['total'],0)
        self.assertEqual(report['without_structural_gaps'],0)
        self.assertEqual(set(report['counts']),set(readiness.GAPS))
        self.assertEqual(report['basis'],'local_structural_fields_only')


@unittest.skipUnless(os.getenv('KIARAD_TEST_BASE_READINESS_DB')=='1','Temporary database opt-in')
class ReadinessDatabaseTests(unittest.TestCase):
    def setUp(self):
        import db
        self.engine=create_engine(db.engine.url,connect_args={'options':'-c search_path=pg_temp -c statement_timeout=10000','connect_timeout':5})
        self.addCleanup(self.engine.dispose)
        self.conn=self.engine.connect();self.addCleanup(self.conn.close);self.addCleanup(self.conn.rollback)
        self.assertEqual(self.conn.exec_driver_sql('SHOW search_path').scalar(),'pg_temp')
        statements=[
            'CREATE TEMP TABLE customers(id INT PRIMARY KEY)',
            'INSERT INTO customers VALUES(1)',
            'CREATE TEMP TABLE users(id INT PRIMARY KEY,salesperson_id INT,role TEXT,is_active INT)',
            "INSERT INTO users VALUES(1,10,'visitor',1),(2,11,'visitor',0)",
            'CREATE TEMP TABLE base_portfolio_assignments(base_source TEXT,base_id INT,salesperson_id INT,ended_at TIMESTAMP)',
            "INSERT INTO base_portfolio_assignments VALUES('pharmacies',1,10,NULL),('pharmacies',1,11,'2020-01-01')",
            'CREATE TEMP TABLE base_coach_profiles(id INT PRIMARY KEY,base_source TEXT,base_id INT,revision INT,payload JSONB)',
        ]
        for source in readiness.BASES:
            statements.append(f'CREATE TEMP TABLE {source}(id INT PRIMARY KEY,name TEXT,city TEXT,type TEXT,latitude FLOAT,longitude FLOAT)')
        statements.extend([
            "INSERT INTO pharmacies VALUES(1,'آزمایشی','کرمان','pharmacy',30,57)",
            "INSERT INTO kerman_bases_manual VALUES(1,'آزمایشی','کرمان','holoo_counterparty',NULL,NULL)",
        ])
        for statement in statements:self.conn.execute(text(statement))
        for ident,payload in [(1,{'customer_id':1,'grade':'unknown'}),(2,{'customer_id':1,'grade':'A','monthly_capacity':'10'})]:
            self.conn.execute(text("INSERT INTO base_coach_profiles VALUES(:id,'pharmacies',1,:id,CAST(:payload AS JSONB))"),{'id':ident,'payload':json.dumps(payload)})

    def test_latest_revision_and_active_assignment_are_used_without_name_merge(self):
        report=readiness.collect_readiness(self.conn)
        self.assertEqual(report['total'],2)
        self.assertEqual(report['without_structural_gaps'],1)
        self.assertEqual(report['counts'],dict.fromkeys(readiness.GAPS,1))
        pharmacy=next(row for row in report['items'] if row['source']=='pharmacies')
        self.assertEqual(pharmacy['missing'],[])
        self.assertNotIn('latitude',pharmacy)

    def test_inactive_or_ambiguous_owner_is_not_ready(self):
        self.conn.execute(text('UPDATE users SET is_active=0'))
        self.assertEqual(readiness.collect_readiness(self.conn)['counts']['owner'],2)
        self.conn.execute(text('UPDATE users SET is_active=1'))
        self.conn.execute(text("INSERT INTO base_portfolio_assignments VALUES('pharmacies',1,11,NULL)"))
        self.assertEqual(readiness.collect_readiness(self.conn)['counts']['owner'],2)

    def test_deleted_customer_and_missing_newest_profile_are_detected(self):
        self.conn.execute(text('DELETE FROM customers'))
        self.conn.execute(text('''INSERT INTO base_coach_profiles VALUES(3,'pharmacies',1,3,'{}')'''))
        report=readiness.collect_readiness(self.conn)
        for gap in ('customer','grade','capacity'):
            self.assertEqual(report['counts'][gap],2)

    def test_query_is_read_only_and_does_not_change_source_records(self):
        self.conn.commit()
        self.conn.execute(text('SET TRANSACTION READ ONLY'))
        self.assertEqual(self.conn.execute(text('SHOW transaction_read_only')).scalar(),'on')
        self.assertEqual(readiness.collect_readiness(self.conn)['total'],2)
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM base_coach_profiles')).scalar(),2)
