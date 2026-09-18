import getpass

from sqlalchemy import text

from db import engine
from operations import hash_password


username = input("Admin username: ").strip().lower()
full_name = input("Admin full name: ").strip()
password = getpass.getpass("Admin password: ")

if len(username) < 3 or len(full_name) < 2 or len(password) < 10:
    raise SystemExit("Username/full name is invalid or password is shorter than 10 characters.")

with engine.begin() as conn:
    conn.execute(
        text("""
            INSERT INTO users (username, password_hash, full_name, role, is_active, created_at)
            VALUES (:username, :password_hash, :full_name, 'ceo', 1, NOW())
            ON CONFLICT (username) DO UPDATE SET
                password_hash=EXCLUDED.password_hash,
                full_name=EXCLUDED.full_name,
                role='ceo',
                is_active=1
        """),
        {
            "username": username,
            "password_hash": hash_password(password),
            "full_name": full_name,
        },
    )

print("CEO account created or updated successfully.")
