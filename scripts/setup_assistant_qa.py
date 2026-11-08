"""Create/seed a dedicated disposable QA database; never writes business DB rows."""
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
from config import DB_CONFIG
from operations import hash_password,create_token

QA_NAME='kiarad_assistant_qa_20261103'
args=dict(host=DB_CONFIG['host'],port=DB_CONFIG['port'],user=DB_CONFIG['user'],password=DB_CONFIG['password'])
root=Path(__file__).resolve().parents[1]

if sys.argv[1]=='create':
    conn=psycopg2.connect(dbname='postgres',**args);conn.autocommit=True
    with conn.cursor() as cur:
        cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',(QA_NAME,))
        if cur.fetchone():raise SystemExit('QA database already exists; refuse to overwrite')
        cur.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(QA_NAME)))
    conn.close()
    print(json.dumps({'database':QA_NAME,'created':True}))
elif sys.argv[1]=='staff':
    conn=psycopg2.connect(dbname=QA_NAME,**args)
    with conn,conn.cursor() as cur:
        cur.execute('SELECT current_database()');assert cur.fetchone()[0]==QA_NAME
        cur.execute("SELECT id FROM users WHERE username='qa_visitor'")
        if not cur.fetchone():
            cur.execute("INSERT INTO salespersons(name) VALUES('ویزیتور تست مستقل') RETURNING id");sid=cur.fetchone()[0]
            cur.execute("INSERT INTO users(username,full_name,password_hash,role,is_active,salesperson_id,password_version,created_at) SELECT 'qa_visitor','ویزیتور تست مستقل',password_hash,'visitor',1,%s,0,NOW() FROM users WHERE username='qa_assistant'",(sid,))
    conn.close();print(json.dumps({'staff_ready':True}))
elif sys.argv[1]=='seed':
    conn=psycopg2.connect(dbname=QA_NAME,**args)
    with conn,conn.cursor() as cur:
        cur.execute('SELECT current_database()');assert cur.fetchone()[0]==QA_NAME
        cur.execute("INSERT INTO salespersons(name) VALUES('پرسنل آزمون دستیار') RETURNING id");sid=cur.fetchone()[0]
        cur.execute("INSERT INTO users(username,full_name,password_hash,role,is_active,salesperson_id,password_version,created_at) VALUES(%s,%s,%s,'ceo',1,%s,0,NOW()) RETURNING id",('qa_assistant','مدیر آزمون',hash_password('qa-only-'+__import__('secrets').token_hex(20)),sid));uid=cur.fetchone()[0]
        cur.execute("INSERT INTO products(code,name,price,price2,stock,min_stock,is_active) VALUES('QA-ONLY-P','کالای آزمون دستیار',100000,120000,100,5,1) RETURNING id");pid=cur.fetchone()[0]
        cur.execute("INSERT INTO customers(code,name,city,credit_limit) VALUES('QA-ONLY-C','مشتری آزمون دستیار','کرمان',0) RETURNING id");cid=cur.fetchone()[0]
    actor={'id':uid,'username':'qa_assistant','full_name':'مدیر آزمون','role':'ceo','salesperson_id':sid,'password_version':0}
    dest=root/'private_exports'/'assistant-qa-session.json';dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps({'database':QA_NAME,'user':actor,'token':create_token(actor),'product_id':pid,'customer_id':cid},ensure_ascii=False),encoding='utf-8')
    conn.close();print(json.dumps({'seeded':True,'only_test_data':True}))
