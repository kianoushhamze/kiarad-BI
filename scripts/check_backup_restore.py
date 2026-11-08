"""Restore a consistent production snapshot into a unique disposable database.

Never restores over the source. Keeps the dump in private_exports; reports no rows.
"""
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
import psycopg2
from psycopg2 import sql
from config import DB_CONFIG


def connect(database):
    return psycopg2.connect(host=DB_CONFIG['host'], port=DB_CONFIG['port'],
                            user=DB_CONFIG['user'], password=DB_CONFIG['password'],
                            database=database, connect_timeout=10)


def counts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        tables = [row[0] for row in cur.fetchall()]
        result = {}
        for table in tables:
            cur.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table)))
            result[table] = cur.fetchone()[0]
        return result


def main():
    ident = uuid.uuid4().hex
    target = 'kiarad_restore_check_' + ident
    assert target != DB_CONFIG['database']
    folder = ROOT / 'private_exports' / 'restore-checks' / ident
    folder.mkdir(parents=True)
    dump = folder / 'database.dump'
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'passed': False,
              'source_modified': False, 'temporary_database_removed': False,
              'dump': str(dump.relative_to(ROOT))}
    created = False
    source = connect(DB_CONFIG['database'])
    admin = connect(DB_CONFIG['database'])
    admin.autocommit = True
    try:
        source.set_session(isolation_level='REPEATABLE READ', readonly=True)
        with source.cursor() as cur:
            cur.execute('SELECT pg_export_snapshot()')
            snapshot = cur.fetchone()[0]
        expected = counts(source)
        with dump.open('wb') as output:
            result = subprocess.run(['docker', 'exec', 'kiarad-postgres', 'pg_dump',
                '-U', DB_CONFIG['user'], '-d', DB_CONFIG['database'], '-Fc',
                '--snapshot', snapshot], stdout=output, stderr=subprocess.PIPE, timeout=300)
        if result.returncode:
            raise RuntimeError('dump_failed')
        source.rollback()
        with admin.cursor() as cur:
            cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(target)))
        created = True
        with dump.open('rb') as archive:
            result = subprocess.run(['docker', 'exec', '-i', 'kiarad-postgres', 'pg_restore',
                '-U', DB_CONFIG['user'], '-d', target, '--exit-on-error'],
                stdin=archive, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=300)
        if result.returncode:
            raise RuntimeError('restore_failed')
        restored = connect(target)
        try:
            actual = counts(restored)
        finally:
            restored.close()
        report.update(tables=len(expected), mismatched_tables=[t for t in set(expected) | set(actual)
            if expected.get(t) != actual.get(t)], dump_bytes=dump.stat().st_size)
        report['passed'] = expected == actual
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        # Never log connection credentials or database contents.
    finally:
        source.close()
        if created:
            assert target.startswith('kiarad_restore_check_') and target != DB_CONFIG['database']
            try:
                with admin.cursor() as cur:
                    cur.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(target)))
                report['temporary_database_removed'] = True
            except Exception:
                report['passed'] = False
                report['cleanup_required'] = target
        admin.close()
        out = ROOT / 'audit-2026-10-23'
        out.mkdir(exist_ok=True)
        (out / 'backup-restore.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
