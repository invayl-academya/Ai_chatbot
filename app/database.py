# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

SQLALCHEMY_DB_URL = "sqlite:///./testdb.db"  # SQLite file in project root

engine = create_engine(
    SQLALCHEMY_DB_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
    future=True,
    echo=False,  # set True to log SQL in dev
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
Base = declarative_base()

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
