import os
import unittest
from sqlalchemy import text
from db import engine
from integrations import migrate_draft_schema


@unittest.skipUnless(os.getenv('KIARAD_TEST_INTEGRATION_DB') == '1', 'Temporary PostgreSQL tables')
class IntegrationSchemaUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.conn=engine.connect()
        self.addCleanup(self.conn.close)
        tx=self.conn.begin()
        self.addCleanup(tx.rollback)

    def test_legacy_identifier_preserved_and_empty_edit_not_resurrected(self):
        self.conn.execute(text("""CREATE TEMP TABLE integration_drafts (id SERIAL PRIMARY KEY,channel TEXT UNIQUE,
            public_identifier VARCHAR(160) NOT NULL,notes TEXT,updated_at TIMESTAMP)"""))
        self.conn.execute(text("INSERT INTO integration_drafts (channel,public_identifier) VALUES ('telegram','public-channel')"))
        migrate_draft_schema(self.conn)
        self.assertEqual(self.conn.execute(text('SELECT account_label FROM integration_drafts')).scalar(),'public-channel')
        self.conn.execute(text("UPDATE integration_drafts SET account_label=''"))
        migrate_draft_schema(self.conn)
        self.assertEqual(self.conn.execute(text('SELECT account_label FROM integration_drafts')).scalar(),'')
        self.conn.execute(text("INSERT INTO integration_drafts (channel,account_label) VALUES ('bale','new-label')"))
        self.assertEqual(self.conn.execute(text('SELECT COUNT(*) FROM integration_drafts')).scalar(),2)

    def test_modern_table_is_unchanged(self):
        self.conn.execute(text("CREATE TEMP TABLE integration_drafts (channel TEXT PRIMARY KEY,account_label VARCHAR(160) NOT NULL DEFAULT '')"))
        self.conn.execute(text("INSERT INTO integration_drafts VALUES ('telegram','kept')"))
        migrate_draft_schema(self.conn)
        migrate_draft_schema(self.conn)
        self.assertEqual(self.conn.execute(text('SELECT account_label FROM integration_drafts')).scalar(),'kept')


if __name__=='__main__':
    unittest.main()
