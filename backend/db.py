import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.environ.get("DATABASE_URL")

if not DB_URL:
    print("WARNING: DATABASE_URL not found in .env. Database connections will fail!")

class DatabaseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._pool = None
        return cls._instance

    def connect(self):
        if not self._pool:
            try:
                self._pool = psycopg2.pool.ThreadedConnectionPool(
                    1, 20, dsn=DB_URL, sslmode='require'
                )
                print("Successfully established PostgreSQL connection pool.")
            except Exception as e:
                print(f"CRITICAL: Error connecting to database: {e}")

    def get_conn(self):
        if not self._pool:
            self.connect()
        return self._pool.getconn()

    def release_conn(self, conn):
        if self._pool:
            self._pool.putconn(conn)

db_mgr = DatabaseManager()

def fetch_all(query, params=None):
    conn = db_mgr.get_conn()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        cursor.close()
        db_mgr.release_conn(conn)

def execute_one(query, params=None):
    conn = db_mgr.get_conn()
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        if cursor.description:
             return cursor.fetchone()
    finally:
        cursor.close()
        db_mgr.release_conn(conn)
