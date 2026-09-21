# -*- coding: utf-8 -*-
import os
import re
import sys

def fix_mojibake(s):
    if not s or not isinstance(s, str):
        return s
    try:
        chars = set('طظغ€ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ¡¢£¤¥¦§¨©ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿')
        if any(c in chars for c in s):
            return s.encode('windows-1256').decode('utf-8')
    except Exception:
        pass
    return s

def fix_py_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return False

    pattern = r'(\"[^\"\r\n]*\"|\'[^\'\r\n]*\')'
    changed = False

    def repl(m):
        nonlocal changed
        raw_str = m.group(0)
        q = raw_str[0]
        inner = raw_str[1:-1]
        fixed_inner = fix_mojibake(inner)
        if fixed_inner != inner:
            changed = True
            return f"{q}{fixed_inner}{q}"
        return raw_str

    new_content = re.sub(pattern, repl, content)
    if changed:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"[OK] Fixed file: {os.path.basename(file_path)}")
        return True
    return False

def main():
    print("=== Starting Kiarad BI Encoding Auto-Fix ===")
    project_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else '.'

    fixed_count = 0
    for root, dirs, files in os.walk(project_dir):
        if any(x in root for x in ['.venv', 'node_modules', '.git']):
            continue
        for file in files:
            if file.endswith('.py') and file != 'fix_all.py':
                path = os.path.join(root, file)
                if fix_py_file(path):
                    fixed_count += 1

    print(f"Total Python files fixed: {fixed_count}")

    try:
        from db import engine
        from sqlalchemy import text
        print("Checking database...")
        with engine.begin() as conn:
            for table in ['recommendations', 'tasks']:
                try:
                    cols_res = conn.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND data_type IN ('text', 'character varying')")).fetchall()
                    cols = [c[0] for c in cols_res]
                    if not cols:
                        continue

                    rows = conn.execute(text(f"SELECT id, {', '.join(cols)} FROM {table}")).mappings().all()
                    db_fixed = 0
                    for row in rows:
                        updatesW = {}
                        for col in cols:
                            val = row[col]
                            fixed_val = fix_mojibake(val)
                            if fixed_val != val:
                                updates[col] = fixed_val
                        if updates:
                            set_clause = ', '.join([f"{c} = :{c}" for c in updates])
                            updates['id'] = row['id']
                            conn.execute(text(f"UPDATE {table} SET {set_clause} WHERE id = :id"), updates)
                            db_fixed += 1
                    if db_fixed > 0:
                        print(f"[OK] Table {table}: {db_fixed} rows fixed.")
                except Exception:
                    pass
    except Exception as e:
        print(f"DB notice: {e}")

    print("=== All fixes completed successfully! ===")

if __name__ == '__main__':
    main()
