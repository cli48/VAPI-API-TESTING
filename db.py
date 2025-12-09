# db.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


def get_db_connection():
    """
    Returns a new psycopg connection.
    Caller is responsible for closing it (or using `with conn:`).
    """
    return psycopg.connect(
        DATABASE_URL,
        autocommit=False  # we manage commits explicitly
    )
