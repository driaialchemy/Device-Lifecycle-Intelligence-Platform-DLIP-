import psycopg2
import psycopg2.extras
import pandas as pd
import os
import json

# CLOUD READY: Looks for environment variable first, falls back to localhost
DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/device_passport")

def get_conn():
    """
    Establishes a connection to the database using the URL from .env
    """
    return psycopg2.connect(DB_URL)

def init_db_schema():
    """
    Resets the database tables. WARNING: Wipes existing data.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Clean slate
            cur.execute("DROP TABLE IF EXISTS tool_events, audit_log, runs, device_registry CASCADE")
            
            # Create Tables
            cur.execute("""
                CREATE TABLE device_registry (
                    device_id VARCHAR(50) PRIMARY KEY, 
                    device_payload JSONB
                )
            """)
            cur.execute("""
                CREATE TABLE runs (
                    run_id VARCHAR(50) PRIMARY KEY, 
                    device_id VARCHAR(50), 
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE audit_log (
                    id SERIAL PRIMARY KEY, 
                    run_id VARCHAR(50), 
                    event_type VARCHAR(50), 
                    payload_json JSONB, 
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            conn.commit()

def list_devices():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM device_registry")
            return cur.fetchall()

def get_device_payload(did):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT device_payload FROM device_registry WHERE device_id=%s", (did,))
            r = cur.fetchone()
            return r['device_payload'] if r else {}

def fetch_runs_for_device(did):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM runs WHERE device_id=%s ORDER BY created_at DESC", (did,))
            return pd.DataFrame(cur.fetchall())

def fetch_audit_chain(rid):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM audit_log WHERE run_id=%s ORDER BY id ASC", (rid,))
            return pd.DataFrame(cur.fetchall())