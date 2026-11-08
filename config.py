import os
from pathlib import Path
from dotenv import dotenv_values

def _env(key, default=""):
    val = os.getenv(key)
    if val:
        return val
    try:
        # Match python-dotenv used by the launchers: strip quoting/BOM and
        # parse inline comments instead of including them in DB credentials.
        values = dotenv_values(Path(__file__).resolve().parent / ".env", encoding="utf-8-sig")
        return values.get(key) or default
    except Exception:
        pass
    return default

DB_CONFIG = {
    "host": _env("DB_HOST", "localhost"),
    "port": int(_env("DB_PORT", "5432")),
    "database": _env("DB_NAME", "kiaradbi"),
    "user": _env("DB_USER", "kiarad"),
    "password": _env("POSTGRES_PASSWORD", ""),
}

# The dashboard uses same-origin /api. Add a separate storefront origin here
# explicitly when deploying it on another hostname.
CORS_ORIGINS = [origin.strip().rstrip("/") for origin in _env(
    "KIARAD_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip() and origin.strip() != "*"]
