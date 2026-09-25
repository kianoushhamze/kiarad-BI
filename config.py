import os

def _env(key, default=""):
    val = os.getenv(key)
    if val:
        return val
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(here, ".env")
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    k, sep, v = line.partition("=")
                    return v.strip()
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
