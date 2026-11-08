import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from config import DB_CONFIG


def get_connection():
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )


DATABASE_URL = URL.create(
    "postgresql+psycopg2",
    username=DB_CONFIG["user"], password=DB_CONFIG["password"],
    host=DB_CONFIG["host"], port=DB_CONFIG["port"], database=DB_CONFIG["database"],
)


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
from sqlalchemy.orm import sessionmaker
SessionLocal = sessionmaker(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
