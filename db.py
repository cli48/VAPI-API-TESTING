# db.py
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not found")

    return psycopg2.connect(db_url, sslmode="require")
