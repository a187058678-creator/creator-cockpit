import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


Base = declarative_base()


def normalize_database_url(raw_url: str | None) -> str:
    if not raw_url:
        return "sqlite:///./creator_cockpit.db"

    if raw_url.startswith("postgresql+psycopg://"):
        return raw_url

    if raw_url.startswith("postgres://"):
        return "postgresql+psycopg://" + raw_url[len("postgres://") :]

    if raw_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw_url[len("postgresql://") :]

    return raw_url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL"))
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app import models

    Base.metadata.create_all(bind=engine)
    ensure_runtime_columns()


def ensure_runtime_columns():
    columns_to_ensure = {
        "asset_records": {
            "group_id": 'ALTER TABLE asset_records ADD COLUMN group_id INTEGER',
        },
        "worker_nodes": {
            "group_id": 'ALTER TABLE worker_nodes ADD COLUMN group_id INTEGER',
            "max_parallel_tasks": 'ALTER TABLE worker_nodes ADD COLUMN max_parallel_tasks INTEGER DEFAULT 1',
            "scheduler_weight": 'ALTER TABLE worker_nodes ADD COLUMN scheduler_weight INTEGER DEFAULT 100',
        },
        "account_groups": {
            "postforme_api_key": "ALTER TABLE account_groups ADD COLUMN postforme_api_key TEXT DEFAULT ''",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, column_map in columns_to_ensure.items():
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in column_map.items():
                if column_name not in existing_columns:
                    connection.execute(text(ddl))
