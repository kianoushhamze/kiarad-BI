"""Apply the explicitly approved six-person roster; refuse deletion of referenced profiles."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from sqlalchemy import text

NAMES = ['سهیل صادق شاه نشین', 'نسترن نجمی', 'محدثه رییسی', 'ویدا فروغی', 'مهران ایرانمنش', 'آرمین کرمانی نژاد']
OLD_IDS = {1, 2, 3, 4}
OLD_NAMES = {'علی حسینی', 'رضا مرادی', 'مهدی صادقی', 'سارا احمدی'}


def main():
    load_dotenv(Path(__file__).with_name('.env'))
    from db import engine
    with engine.begin() as conn:
        conn.execute(text('LOCK TABLE salespersons IN SHARE ROW EXCLUSIVE MODE'))
        rows = [dict(row) for row in conn.execute(text('SELECT * FROM salespersons ORDER BY id FOR UPDATE')).mappings()]
        old = [row for row in rows if row['id'] in OLD_IDS]
        if any(row['name'] not in OLD_NAMES for row in old):
            raise RuntimeError('Unexpected profile identity; no changes applied')
        refs = conn.execute(text("""SELECT kcu.table_name,kcu.column_name FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name AND tc.constraint_schema=kcu.constraint_schema
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name=tc.constraint_name AND ccu.constraint_schema=tc.constraint_schema
            WHERE tc.constraint_type='FOREIGN KEY' AND ccu.table_name='salespersons' AND tc.table_schema='public'""")).mappings().all()
        dependencies = []
        for ref in refs:
            table = ref['table_name'].replace('"','""')
            column = ref['column_name'].replace('"','""')
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IN (1,2,3,4)')).scalar()
            if count and table != 'salesperson_locations':
                dependencies.append({'table':table,'count':count})
        if dependencies:
            print(json.dumps({'blocked_dependencies':dependencies}, ensure_ascii=False))
            raise RuntimeError('Referenced records must be preserved; no changes applied')
        backup = Path(__file__).parent / 'backups' / 'staff-roster'
        backup.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(ZoneInfo('Asia/Tehran')).strftime('%Y%m%d-%H%M%S-%f')
        # Backup is data output, not source code. Exclusive creation prevents overwrite.
        with (backup / f'profiles-{stamp}.json').open('x',encoding='utf-8') as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2, default=str)
        locations = [dict(row) for row in conn.execute(text('SELECT * FROM salesperson_locations WHERE salesperson_id IN (1,2,3,4)')).mappings()]
        with (backup / f'locations-{stamp}.json').open('x',encoding='utf-8') as handle:
            json.dump(locations, handle, ensure_ascii=False, indent=2, default=str)
        for name in NAMES:
            if not conn.execute(text('SELECT id FROM salespersons WHERE name=:name'), {'name':name}).first():
                conn.execute(text('INSERT INTO salespersons (name,phone) VALUES (:name,NULL)'), {'name':name})
        conn.execute(text('DELETE FROM salesperson_locations WHERE salesperson_id IN (1,2,3,4)'))
        conn.execute(text('DELETE FROM salespersons WHERE id IN (1,2,3,4)'))
        final = [dict(row) for row in conn.execute(text('SELECT id,name FROM salespersons ORDER BY id')).mappings()]
        if len(final) != 6 or {row['name'] for row in final} != set(NAMES):
            raise RuntimeError('Unexpected final roster; transaction rolled back')
    print(json.dumps({'profiles':final,'backup_directory':str(backup)},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    main()
