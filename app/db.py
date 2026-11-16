
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is missing. Check your .env file."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    connect_args={"connect_timeout": 10},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


class Base(DeclarativeBase):
    pass


def check_database_connection():
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
