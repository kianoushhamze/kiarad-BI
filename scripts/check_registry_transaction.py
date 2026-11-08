"""Exercise import/repeat/delete against PostgreSQL, then roll everything back."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import sys
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from fastapi import HTTPException
import field_intelligence as field
from db import engine


def main():
    suffix=uuid4().hex
    dataset={'observed_at':'2026-11-02','notice':'transaction test','batches':[{'id':'test','source_url':'https://example.invalid/test'}],
             'items':[{'source_id':'test-'+suffix,'batch_id':'test','name':'آزمون موقت '+suffix,'city':'شهر آزمایشی',
                       'phone':'','category':'pharmacy','source_row':1}]}
    with engine.connect() as conn:
        transaction=conn.begin()
        @contextmanager
        def begin():
            yield conn
        try:
            with patch.object(field,'engine',SimpleNamespace(begin=begin)), patch.object(field,'load_registry',return_value=dataset):
                actor={'id':1,'role':'ceo'}
                data=field.RegistryCustomerImport(source_id='test-'+suffix,confirm=True)
                first=field.import_registry_customer(data,actor)
                again=field.import_registry_customer(data,actor)
                assert first['status']=='created' and again['customer_id']==first['customer_id'] and again['status']=='already_imported'
                # A CASCADE relationship must block removal rather than delete its history.
                history='registry_test_history_'+suffix
                conn.execute(text(f'CREATE TABLE {history}(customer_id INT REFERENCES customers(id) ON DELETE CASCADE)'))
                conn.execute(text(f'INSERT INTO {history}(customer_id) VALUES(:id)'),{'id':first['customer_id']})
                try:
                    field.delete_registry_customer(first['customer_id'],actor)
                    raise AssertionError('related_history_was_not_protected')
                except HTTPException as error:
                    assert error.status_code==409
                conn.execute(text(f'DELETE FROM {history}'))
                assert field.delete_registry_customer(first['customer_id'],actor)['status']=='deleted'
            print(json.dumps({'checks':4,'failures':0,'rolled_back':True}))
        finally:
            transaction.rollback()


if __name__=='__main__':main()
