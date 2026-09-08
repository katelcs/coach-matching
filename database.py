import os
import psycopg2
import psycopg2.extras
from flask import g

# Railway sometimes gives postgres:// — psycopg2 needs postgresql://
_RAW_URL = os.environ.get("DATABASE_URL", "")
DATABASE_URL = _RAW_URL.replace("postgres://", "postgresql://", 1) if _RAW_URL.startswith("postgres://") else _RAW_URL


class _DB:
    """Thin wrapper so app.py can call db.execute() / db.commit() without changes."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        sql = sql.replace("?", "%s")          # sqlite uses ?, postgres uses %s
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()


def get_db():
    if "db" not in g:
        conn = psycopg2.connect(DATABASE_URL,
                                cursor_factory=psycopg2.extras.RealDictCursor)
        g.db = _DB(conn)
        g._db_conn = conn
    return g.db


def close_db(e=None):
    conn = g.pop("_db_conn", None)
    if conn is not None:
        conn.close()


def init_db():
    conn = psycopg2.connect(DATABASE_URL,
                            cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS student_submissions (
            id                      SERIAL PRIMARY KEY,
            name                    TEXT NOT NULL,
            email                   TEXT NOT NULL,
            location                TEXT,
            timezone                TEXT,
            countries               TEXT,
            motivation              TEXT,
            study_background        TEXT,
            accommodations          TEXT,
            agreement_acknowledged  BOOLEAN DEFAULT FALSE,
            assessment_acknowledged BOOLEAN DEFAULT FALSE,
            availability            TEXT,
            notes                   TEXT,
            created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS coach_submissions (
            id          SERIAL PRIMARY KEY,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL UNIQUE,
            timezone    TEXT,
            country     TEXT,
            availability TEXT,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Migrations for columns added after initial deploy
    new_columns = [
        ("notes",                    "TEXT"),
        ("location",                 "TEXT"),
        ("motivation",               "TEXT"),
        ("study_background",         "TEXT"),
        ("accommodations",           "TEXT"),
        ("agreement_acknowledged",   "BOOLEAN DEFAULT FALSE"),
        ("assessment_acknowledged",  "BOOLEAN DEFAULT FALSE"),
    ]
    for col, col_type in new_columns:
        try:
            cur.execute(f"ALTER TABLE student_submissions ADD COLUMN {col} {col_type}")
            conn.commit()
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()

    # Migrations for coach_submissions columns added after initial deploy
    coach_columns = [
        ("timezone", "TEXT"),
    ]
    for col, col_type in coach_columns:
        try:
            cur.execute(f"ALTER TABLE coach_submissions ADD COLUMN {col} {col_type}")
            conn.commit()
        except psycopg2.errors.DuplicateColumn:
            conn.rollback()

    cur.close()
    conn.close()
