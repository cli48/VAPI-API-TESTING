# db.py
import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not found")

    # psycopg3 connect
    conn = psycopg.connect(
        db_url,
        sslmode="require",
        row_factory=dict_row,   # rows as dicts if you want
    )
    return conn
