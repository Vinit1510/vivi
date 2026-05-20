import os
import pandas as pd
import numpy as np
import threading
from datetime import datetime, timezone, timedelta
import json
from dotenv import load_dotenv

load_dotenv()

# Thread lock to guarantee safe, race-free Excel read/writes
excel_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Check EXTRACTED first, then root folder fallback
ROUNDS_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "EXTRACTED", "rounds.xlsx"))
if not os.path.exists(ROUNDS_PATH):
    ROUNDS_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "rounds.xlsx"))

PREDS_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "EXTRACTED", "predictions.xlsx"))
if not os.path.exists(PREDS_PATH):
    PREDS_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "predictions.xlsx"))

CONFIG_PATH = os.path.abspath(os.path.join(BASE_DIR, "config.json"))

import time

class DbCache:
    def __init__(self):
        self.latest_round_id = None
        self.latest_round_id_time = 0
        
        self.total_rounds_count = None
        self.total_rounds_count_time = 0
        
        self.latest_rounds = {}
        self.available_dates = None
        self.available_dates_time = 0
        
        self.hourly_history = {}
        
    def clear(self):
        self.latest_round_id = None
        self.total_rounds_count = None
        self.latest_rounds.clear()
        self.available_dates = None
        self.hourly_history.clear()
        print("[DbCache] Cache cleared successfully due to database mutation.")

db_cache = DbCache()


# ==========================================================================
# POSTGRESQL HYBRID DATABASE ABSTRACTION LAYER (NEON COMPATIBLE)
# ==========================================================================
DB_URL = os.environ.get("DATABASE_URL")
use_postgres = bool(DB_URL)
pg_pool = None

if use_postgres:
    try:
        import psycopg2
        from psycopg2 import pool
        pg_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, dsn=DB_URL, sslmode='require')
        print("[PostgresDB] ThreadedConnectionPool successfully initialized.")
        
        # Proactively verify/create tables
        conn = pg_pool.getconn()
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rounds (
                id SERIAL PRIMARY KEY,
                period_id VARCHAR(50) UNIQUE NOT NULL,
                number INTEGER NOT NULL,
                size VARCHAR(10) NOT NULL,
                color VARCHAR(20) NOT NULL,
                raw_json TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS predictions (
                id SERIAL PRIMARY KEY,
                period_id VARCHAR(50) UNIQUE NOT NULL,
                predicted_size VARCHAR(10),
                predicted_color VARCHAR(20),
                size_confidence REAL,
                color_confidence REAL,
                actual_size VARCHAR(10),
                actual_color VARCHAR(20),
                size_result VARCHAR(10),
                color_result VARCHAR(20),
                is_processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS system_config (
                key VARCHAR(50) PRIMARY KEY,
                value VARCHAR(100) NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # ==========================================================================
        # ONE-CLICK AUTOMATIC DATA SEEDER / MIGRATOR
        # ==========================================================================
        # Check if Postgres database is empty
        cursor.execute("SELECT COUNT(*) FROM rounds;")
        pg_count = cursor.fetchone()[0]
        
        if pg_count == 0:
            print("[PostgresDB Sync] PostgreSQL is empty. Checking for local Excel data to migrate...")
            
            # Migrate Rounds
            if os.path.exists(ROUNDS_PATH):
                try:
                    df_r = pd.read_excel(ROUNDS_PATH, dtype={'period_id': str}, engine='openpyxl')
                    if len(df_r) > 0:
                        print(f"[PostgresDB Sync] Found {len(df_r)} local rounds. Beginning batch migration...")
                        rounds_to_insert = []
                        for _, row in df_r.iterrows():
                            p_id = str(row['period_id']).strip().split('.')[0]
                            num = int(row['number'])
                            sz = str(row['size'])
                            cl = str(row['color'])
                            raw = str(row['raw_json']) if not pd.isnull(row['raw_json']) else None
                            cr = str(row['created_at']) if not pd.isnull(row['created_at']) else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
                            rounds_to_insert.append((p_id, num, sz, cl, raw, cr))
                        
                        cursor.executemany("""
                            INSERT INTO rounds (period_id, number, size, color, raw_json, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            ON CONFLICT (period_id) DO NOTHING;
                        """, rounds_to_insert)
                        print(f"[PostgresDB Sync] Successfully migrated {len(df_r)} historical rounds to Neon PostgreSQL!")
                except Exception as ex:
                    print(f"[PostgresDB Sync Error] Failed migrating rounds: {ex}")
            
            # Migrate Predictions
            if os.path.exists(PREDS_PATH):
                try:
                    df_p = pd.read_excel(PREDS_PATH, dtype={'period_id': str}, engine='openpyxl')
                    if len(df_p) > 0:
                        print(f"[PostgresDB Sync] Found {len(df_p)} local predictions. Migrating...")
                        preds_to_insert = []
                        for _, row in df_p.iterrows():
                            p_id = str(row['period_id']).strip().split('.')[0]
                            p_sz = str(row['predicted_size']) if not pd.isnull(row['predicted_size']) else None
                            p_cl = str(row['predicted_color']) if not pd.isnull(row['predicted_color']) else None
                            sz_cf = float(row['size_confidence']) if not pd.isnull(row['size_confidence']) else None
                            cl_cf = float(row['color_confidence']) if not pd.isnull(row['color_confidence']) else None
                            a_sz = str(row['actual_size']) if not pd.isnull(row['actual_size']) else None
                            a_cl = str(row['actual_color']) if not pd.isnull(row['actual_color']) else None
                            sz_rs = str(row['size_result']) if not pd.isnull(row['size_result']) else None
                            cl_rs = str(row['color_result']) if not pd.isnull(row['color_result']) else None
                            is_pr = bool(row['is_processed']) if not pd.isnull(row['is_processed']) else False
                            cr = str(row['created_at']) if not pd.isnull(row['created_at']) else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            preds_to_insert.append((p_id, p_sz, p_cl, sz_cf, cl_cf, a_sz, a_cl, sz_rs, cl_rs, is_pr, cr))
                        
                        cursor.executemany("""
                            INSERT INTO predictions (period_id, predicted_size, predicted_color, size_confidence, color_confidence, actual_size, actual_color, size_result, color_result, is_processed, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (period_id) DO NOTHING;
                        """, preds_to_insert)
                        print(f"[PostgresDB Sync] Successfully migrated {len(df_p)} predictions to Neon PostgreSQL!")
                except Exception as ex:
                    print(f"[PostgresDB Sync Error] Failed migrating predictions: {ex}")

        cursor.close()
        pg_pool.putconn(conn)
        print("[PostgresDB] Neon Tables verified and ready.")
    except Exception as e:
        print(f"[PostgresDB Warning] Failed to initialize Postgres: {e}. Falling back to Excel.")
        use_postgres = False

def pg_execute(query, params=None, fetch=None):
    if not pg_pool or not use_postgres:
        raise RuntimeError("Postgres database pool is not active or has been disabled.")
    conn = pg_pool.getconn()
    try:
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        if fetch == 'one':
            return cursor.fetchone()
        elif fetch == 'all':
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        return None
    finally:
        cursor.close()
        pg_pool.putconn(conn)

# ==========================================================================
# EXCEL READ/WRITE ABSTRACTION LAYER
# ==========================================================================
def load_rounds():
    if not os.path.exists(ROUNDS_PATH):
        # Create empty rounds sheet
        df = pd.DataFrame(columns=['id', 'period_id', 'number', 'size', 'color', 'raw_json', 'created_at'])
        df.to_excel(ROUNDS_PATH, index=False, engine='openpyxl')
        return df
    
    # Read period_id STRICTLY as string to prevent float64 rounding truncation!
    df = pd.read_excel(ROUNDS_PATH, dtype={'period_id': str}, engine='openpyxl')
    if 'period_id' in df.columns:
        # Clean any float representations like .0 or empty spaces
        df['period_id'] = df['period_id'].astype(str).str.strip().str.split('.').str[0]
        df = df[df['period_id'] != 'nan']
        df = df.drop_duplicates(subset=['period_id'], keep='last')
    return df

def save_rounds(df):
    if 'period_id' in df.columns:
        df['period_id'] = df['period_id'].astype(str).str.strip().str.split('.').str[0]
    df.to_excel(ROUNDS_PATH, index=False, engine='openpyxl')


def load_preds():
    if not os.path.exists(PREDS_PATH):
        df = pd.DataFrame(columns=[
            'id', 'period_id', 'predicted_size', 'predicted_color', 
            'size_confidence', 'color_confidence', 'actual_size', 
            'actual_color', 'size_result', 'color_result', 
            'is_processed', 'created_at'
        ])
        df.to_excel(PREDS_PATH, index=False, engine='openpyxl')
        return df
        
    df = pd.read_excel(PREDS_PATH, dtype={'period_id': str}, engine='openpyxl')
    if 'period_id' in df.columns:
        df['period_id'] = df['period_id'].astype(str).str.strip().str.split('.').str[0]
        df = df[df['period_id'] != 'nan']
        df = df.drop_duplicates(subset=['period_id'], keep='last')
    return df

def save_preds(df):
    if 'period_id' in df.columns:
         df['period_id'] = df['period_id'].astype(str).str.strip().str.split('.').str[0]
    df.to_excel(PREDS_PATH, index=False, engine='openpyxl')

# ==========================================================================
# PUBLIC INTERFACE FOR BACKEND SYSTEMS
# ==========================================================================
def get_system_config(key, default='false'):
    global use_postgres
    if use_postgres:
        try:
            res = pg_execute("SELECT value FROM system_config WHERE key = %s", (key,), fetch='one')
            return res[0] if res else default
        except Exception as e:
            print(f"[PostgresDB Failover] get_system_config failed: {e}. Switching to Excel.")
            use_postgres = False
            
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                data = json.load(f)
                return data.get(key, default)
        return default
    except Exception:
        return default

def set_system_config(key, value):
    global use_postgres
    if use_postgres:
        try:
            pg_execute("""
                INSERT INTO system_config (key, value, updated_at)
                VALUES (%s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
            """, (key, str(value)))
            return True
        except Exception as e:
            print(f"[PostgresDB Failover] set_system_config failed: {e}. Switching to Excel.")
            use_postgres = False
            
    try:
        data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                data = json.load(f)
        data[key] = str(value)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(data, f)
        return True
    except Exception:
        return False

def get_total_rounds_count():
    global use_postgres
    now = time.time()
    if db_cache.total_rounds_count is not None and (now - db_cache.total_rounds_count_time < 3.0):
        return db_cache.total_rounds_count
        
    val = 0
    if use_postgres:
        try:
            res = pg_execute("SELECT COUNT(*) FROM rounds;", fetch='one')
            val = res[0] if res else 0
        except Exception as e:
            print(f"[PostgresDB Failover] get_total_rounds_count failed: {e}. Switching to Excel.")
            use_postgres = False
            
    if not use_postgres:
        with excel_lock:
            try:
                df = load_rounds()
                val = len(df)
            except Exception:
                val = 0
                
    db_cache.total_rounds_count = val
    db_cache.total_rounds_count_time = now
    return val

def get_latest_round_id():
    global use_postgres
    now = time.time()
    if db_cache.latest_round_id is not None and (now - db_cache.latest_round_id_time < 3.0):
        return db_cache.latest_round_id
        
    val = 0
    if use_postgres:
        try:
            res = pg_execute("SELECT period_id FROM rounds ORDER BY period_id DESC LIMIT 1;", fetch='one')
            val = int(res[0]) if res else 0
        except Exception as e:
            print(f"[PostgresDB Failover] get_latest_round_id failed: {e}. Switching to Excel.")
            use_postgres = False
            
    if not use_postgres:
        with excel_lock:
            try:
                df = load_rounds()
                if len(df) > 0:
                    nums = pd.to_numeric(df['period_id'], errors='coerce').dropna()
                    if len(nums) > 0:
                        val = int(nums.max())
            except Exception:
                val = 0
                
    db_cache.latest_round_id = val
    db_cache.latest_round_id_time = now
    return val

def add_round(period_id, number, size, color, raw_json):
    global use_postgres
    if use_postgres:
        try:
            pg_execute("""
                INSERT INTO rounds (period_id, number, size, color, raw_json)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (period_id) DO NOTHING;
            """, (str(period_id), int(number), str(size), str(color), str(raw_json)))
            db_cache.clear()
            return True
        except Exception as e:
            print(f"[PostgresDB Failover] add_round failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_rounds()
            period_id_str = str(period_id).strip().split('.')[0]
            if period_id_str in df['period_id'].values:
                return False # Duplicate
            
            next_id = int(df['id'].max() + 1) if len(df) > 0 else 1
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
            
            new_row = {
                'id': next_id,
                'period_id': period_id_str,
                'number': int(number),
                'size': str(size),
                'color': str(color),
                'raw_json': str(raw_json),
                'created_at': now_str
            }
            
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_rounds(df)
            db_cache.clear()
            return True
        except Exception as ex:
            print(f"[ExcelDB Error] add_round: {ex}")
            return False

def add_prediction(period_id, predicted_size, predicted_color, size_confidence, color_confidence):
    global use_postgres
    if use_postgres:
        try:
            pg_execute("""
                INSERT INTO predictions (period_id, predicted_size, predicted_color, size_confidence, color_confidence)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (period_id) DO NOTHING;
            """, (str(period_id), str(predicted_size), str(predicted_color), float(size_confidence), float(color_confidence)))
            db_cache.clear()
            return True
        except Exception as e:
            print(f"[PostgresDB Failover] add_prediction failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_preds()
            period_id_str = str(period_id).strip().split('.')[0]
            if period_id_str in df['period_id'].values:
                return False # Duplicate
            
            next_id = int(df['id'].max() + 1) if len(df) > 0 else 1
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            new_row = {
                'id': next_id,
                'period_id': period_id_str,
                'predicted_size': str(predicted_size),
                'predicted_color': str(predicted_color),
                'size_confidence': float(size_confidence),
                'color_confidence': float(color_confidence),
                'actual_size': None,
                'actual_color': None,
                'size_result': None,
                'color_result': None,
                'is_processed': False,
                'created_at': now_str
            }
            
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            save_preds(df)
            db_cache.clear()
            return True
        except Exception as ex:
            print(f"[ExcelDB Error] add_prediction: {ex}")
            return False


def check_prediction_exists(period_id):
    global use_postgres
    if use_postgres:
        try:
            res = pg_execute("SELECT EXISTS(SELECT 1 FROM predictions WHERE period_id = %s);", (str(period_id),), fetch='one')
            return bool(res[0]) if res else False
        except Exception as e:
            print(f"[PostgresDB Failover] check_prediction_exists failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_preds()
            period_id_str = str(period_id).strip().split('.')[0]
            return period_id_str in df['period_id'].values
        except Exception:
            return False

def get_prediction(period_id):
    global use_postgres
    if use_postgres:
        try:
            res = pg_execute("SELECT predicted_size, predicted_color, size_confidence, color_confidence FROM predictions WHERE period_id = %s;", (str(period_id),), fetch='one')
            if res:
                return {
                    "predicted_size": res[0],
                    "predicted_color": res[1],
                    "size_confidence": res[2],
                    "color_confidence": res[3]
                }
            return None
        except Exception as e:
            print(f"[PostgresDB Failover] get_prediction failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_preds()
            period_id_str = str(period_id).strip().split('.')[0]
            res = df[df['period_id'] == period_id_str]
            if len(res) > 0:
                row = res.iloc[0]
                return {
                    "predicted_size": row['predicted_size'],
                    "predicted_color": row['predicted_color'],
                    "size_confidence": row['size_confidence'],
                    "color_confidence": row['color_confidence']
                }
            return None
        except Exception:
            return None

def update_prediction_outcomes(period_id, actual_size, actual_color):
    global use_postgres
    if use_postgres:
        try:
            pred = pg_execute("SELECT predicted_size, predicted_color FROM predictions WHERE period_id = %s", (str(period_id),), fetch='one')
            if pred:
                pred_size, pred_color = pred[0], pred[1]
                size_res = "WIN" if str(pred_size).strip().lower() == str(actual_size).strip().lower() else "LOSS"
                color_res = "WIN" if str(pred_color).strip().lower() in str(actual_color).strip().lower() else "LOSS"
                pg_execute("""
                    UPDATE predictions 
                    SET actual_size = %s, actual_color = %s, size_result = %s, color_result = %s, is_processed = TRUE 
                    WHERE period_id = %s;
                """, (str(actual_size), str(actual_color), size_res, color_res, str(period_id)))
                return True
            return False
        except Exception as e:
            print(f"[PostgresDB Failover] update_prediction_outcomes failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_preds()
            period_id_str = str(period_id).strip().split('.')[0]
            idx = df[df['period_id'] == period_id_str].index
            if len(idx) > 0:
                p_idx = idx[0]
                pred_size = df.loc[p_idx, 'predicted_size']
                pred_color = df.loc[p_idx, 'predicted_color']
                
                size_res = "WIN" if str(pred_size).strip().lower() == str(actual_size).strip().lower() else "LOSS"
                color_res = "WIN" if str(pred_color).strip().lower() in str(actual_color).strip().lower() else "LOSS"
                
                df.loc[p_idx, 'actual_size'] = str(actual_size)
                df.loc[p_idx, 'actual_color'] = str(actual_color)
                df.loc[p_idx, 'size_result'] = size_res
                df.loc[p_idx, 'color_result'] = color_res
                df.loc[p_idx, 'is_processed'] = True
                save_preds(df)
                return True
            return False
        except Exception as ex:
            print(f"[ExcelDB Error] update_prediction_outcomes: {ex}")
            return False

def get_prediction_results_map():
    """Returns a dictionary mapping period_id -> size_result and color_result for RL retraining."""
    global use_postgres
    if use_postgres:
        try:
            res = pg_execute("SELECT period_id, size_result, color_result FROM predictions WHERE is_processed = TRUE;", fetch='all')
            return {str(r['period_id']): (r['size_result'], r['color_result']) for r in res} if res else {}
        except Exception:
            pass
            
    with excel_lock:
        try:
            df = load_preds()
            df_proc = df[df['is_processed'] == True]
            return {str(row['period_id']).strip().split('.')[0]: (row['size_result'], row['color_result']) for _, row in df_proc.iterrows()}
        except Exception:
            return {}

def get_accuracy_stats():
    global use_postgres
    if use_postgres:
        try:
            res = pg_execute("""
                SELECT 
                    COUNT(*) filter (WHERE size_result = 'WIN') as size_wins,
                    COUNT(*) filter (WHERE color_result = 'WIN') as color_wins,
                    COUNT(*) filter (WHERE is_processed = TRUE) as total_preds
                FROM predictions
            """, fetch='one')
            if res and res[2] > 0:
                return {
                    "size_wins": int(res[0]),
                    "color_wins": int(res[1]),
                    "total_preds": int(res[2])
                }
            return {"size_wins": 0, "color_wins": 0, "total_preds": 0}
        except Exception as e:
            print(f"[PostgresDB Failover] get_accuracy_stats failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_preds()
            processed = df[df['is_processed'] == True]
            total = len(processed)
            if total == 0:
                return {"size_wins": 0, "color_wins": 0, "total_preds": 0}
            
            size_wins = len(processed[processed['size_result'] == 'WIN'])
            color_wins = len(processed[processed['color_result'] == 'WIN'])
            return {
                "size_wins": size_wins,
                "color_wins": color_wins,
                "total_preds": total
            }
        except Exception:
            return {"size_wins": 0, "color_wins": 0, "total_preds": 0}

def get_available_dates():
    global use_postgres
    if use_postgres:
        try:
            res = pg_execute("""
                SELECT DISTINCT DATE_TRUNC('day', created_at AT TIME ZONE 'Asia/Kolkata')::date as valid_date 
                FROM rounds 
                ORDER BY valid_date DESC 
                LIMIT 30;
            """, fetch='all')
            return [str(r["valid_date"]) for r in res]
        except Exception as e:
            print(f"[PostgresDB Failover] get_available_dates failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = load_rounds()
            if len(df) == 0:
                return []
            
            # Parse created_at timestamps, localizing to Asia/Kolkata (IST)
            df['parsed_time'] = pd.to_datetime(df['created_at'], errors='coerce')
            df['ist_time'] = df['parsed_time'].dt.tz_convert('Asia/Kolkata') if df['parsed_time'].dt.tz is not None else df['parsed_time'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            
            # Extract date strings
            dates = df['ist_time'].dt.strftime("%Y-%m-%d").dropna().unique()
            sorted_dates = sorted(list(dates), reverse=True)
            return sorted_dates[:30]
        except Exception as e:
            print(f"[ExcelDB Error] get_available_dates: {e}")
            return []

def get_hourly_history(target_date):
    global use_postgres
    if use_postgres:
        try:
            query = """
                WITH ist_rounds AS (
                    SELECT 
                        r.period_id, r.number, r.size, r.color, 
                        r.created_at AT TIME ZONE 'Asia/Kolkata' as local_time,
                        p.predicted_size, p.predicted_color,
                        p.size_result, p.color_result,
                        p.size_confidence, p.color_confidence
                    FROM rounds r
                    LEFT JOIN predictions p ON r.period_id = p.period_id
                )
                SELECT 
                    EXTRACT(HOUR FROM local_time)::INTEGER as hour,
                    COUNT(*) as count,
                    COUNT(*) FILTER (WHERE size_result IS NOT NULL) as total_preds,
                    COUNT(*) FILTER (WHERE size_result = 'WIN') as size_wins,
                    COUNT(*) FILTER (WHERE color_result = 'WIN') as color_wins,
                    JSON_AGG(
                        JSON_BUILD_OBJECT(
                            'period_id', period_id::TEXT,
                            'number', number,
                            'size', size,
                            'color', color,
                            'time', local_time::time,
                            'p_size', predicted_size,
                            'p_color', predicted_color,
                            'r_size', size_result,
                            'r_color', color_result,
                            'p_size_conf', size_confidence,
                            'p_color_conf', color_confidence
                        ) ORDER BY period_id DESC
                    ) as rounds
                FROM ist_rounds
                WHERE local_time::date = %s
                GROUP BY EXTRACT(HOUR FROM local_time)
                ORDER BY hour DESC;
            """
            results = pg_execute(query, (target_date,), fetch='all')
            
            history = []
            for r in results:
                history.append({
                    'hour': int(r['hour']),
                    'count': int(r['count']),
                    'total_preds': int(r['total_preds'] or 0),
                    'size_wins': int(r['size_wins'] or 0),
                    'color_wins': int(r['color_wins'] or 0),
                    'rounds': r['rounds']
                })
            return history
        except Exception as e:
            print(f"[PostgresDB Failover] get_hourly_history failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df_rounds = load_rounds()
            df_preds = load_preds()
            
            if len(df_rounds) == 0:
                return []
                
            # Perform JOIN in pandas
            df_merged = pd.merge(df_rounds, df_preds, on='period_id', how='left', suffixes=('', '_pred'))
            
            # Parse localized time
            df_merged['parsed_time'] = pd.to_datetime(df_merged['created_at'], errors='coerce')
            df_merged['ist_time'] = df_merged['parsed_time'].dt.tz_convert('Asia/Kolkata') if df_merged['parsed_time'].dt.tz is not None else df_merged['parsed_time'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            
            # Filter by target date
            df_filtered = df_merged[df_merged['ist_time'].dt.strftime("%Y-%m-%d") == str(target_date)]
            
            if len(df_filtered) == 0:
                return []
                
            # Extract hours
            df_filtered['hour'] = df_filtered['ist_time'].dt.hour
            
            hourly_data = []
            for hour, group in df_filtered.groupby('hour'):
                # Sort from newest to oldest within each hour
                group_sorted = group.sort_values('period_id', ascending=False)
                
                rounds_list = []
                for _, row in group_sorted.iterrows():
                    time_str = row['ist_time'].strftime("%H:%M:%S") if not pd.isnull(row['ist_time']) else "00:00:00"
                    
                    rounds_list.append({
                        'period_id': str(row['period_id']),
                        'number': int(row['number']),
                        'size': str(row['size']),
                        'color': str(row['color']),
                        'time': time_str,
                        'p_size': row['predicted_size'] if not pd.isnull(row['predicted_size']) else None,
                        'p_color': row['predicted_color'] if not pd.isnull(row['predicted_color']) else None,
                        'r_size': row['size_result'] if not pd.isnull(row['size_result']) else None,
                        'r_color': row['color_result'] if not pd.isnull(row['color_result']) else None,
                        'p_size_conf': float(row['size_confidence']) if not pd.isnull(row['size_confidence']) else None,
                        'p_color_conf': float(row['color_confidence']) if not pd.isnull(row['color_confidence']) else None,
                    })
                
                # Calculate counts
                total_preds = len(group_sorted[group_sorted['is_processed'] == True])
                size_wins = len(group_sorted[group_sorted['size_result'] == 'WIN'])
                color_wins = len(group_sorted[group_sorted['color_result'] == 'WIN'])
                
                hourly_data.append({
                    'hour': int(hour),
                    'count': len(group_sorted),
                    'total_preds': total_preds,
                    'size_wins': size_wins,
                    'color_wins': color_wins,
                    'rounds': rounds_list
                })
                
            # Sort hours descending
            hourly_data = sorted(hourly_data, key=lambda x: x['hour'], reverse=True)
            return hourly_data
            
        except Exception as e:
            print(f"[ExcelDB Error] get_hourly_history: {e}")
            import traceback
            traceback.print_exc()
            return []

def get_latest_rounds(limit=30):
    global use_postgres
    now = time.time()
    cached = db_cache.latest_rounds.get(limit)
    if cached and (now - cached[0] < 3.0):
        return cached[1]
        
    val = []
    if use_postgres:
        try:
            res = pg_execute("SELECT period_id, number, size, color FROM rounds ORDER BY period_id DESC LIMIT %s", (limit,), fetch='all')
            val = [{
                'period_id': str(r['period_id']),
                'number': int(r['number']),
                'size': str(r['size']),
                'color': str(r['color'])
            } for r in res]
        except Exception as e:
            print(f"[PostgresDB Failover] get_latest_rounds failed: {e}. Switching to Excel.")
            use_postgres = False
            
    if not use_postgres:
        with excel_lock:
            try:
                df = load_rounds()
                if len(df) == 0:
                    val = []
                else:
                    # Sort from newest to oldest
                    df['num_period'] = pd.to_numeric(df['period_id'], errors='coerce')
                    df_sorted = df.sort_values("num_period", ascending=False).head(limit)
                    
                    rounds_list = []
                    for _, row in df_sorted.iterrows():
                        rounds_list.append({
                            'period_id': str(row['period_id']),
                            'number': int(row['number']),
                            'size': str(row['size']),
                            'color': str(row['color'])
                        })
                    val = rounds_list
            except Exception:
                val = []
                
    db_cache.latest_rounds[limit] = (now, val)
    return val

def clear_predictions_db():
    """Wipes all records from the predictions database to reset sessions cleanly."""
    global use_postgres
    if use_postgres:
        try:
            pg_execute("TRUNCATE TABLE predictions;")
            db_cache.clear()
            return True
        except Exception as e:
            print(f"[PostgresDB Failover] clear_predictions_db failed: {e}. Switching to Excel.")
            use_postgres = False
            
    with excel_lock:
        try:
            df = pd.DataFrame(columns=[
                'id', 'period_id', 'predicted_size', 'predicted_color',
                'size_confidence', 'color_confidence', 'actual_size',
                'actual_color', 'size_result', 'color_result', 'is_processed', 'created_at'
            ])
            save_preds(df)
            db_cache.clear()
            return True
        except Exception as e:
            print(f"[ExcelDB Error] clear_predictions_db: {e}")
            return False

def calculate_hourly_profile():
    """Analyzes the 24-hour predictive bias profile of Wingo VIVI over all history."""
    global use_postgres
    predictions_list = []
    if use_postgres:
        try:
            res = pg_execute("SELECT period_id, size_result, color_result, created_at FROM predictions WHERE is_processed = TRUE;", fetch='all')
            predictions_list = [{
                'period_id': str(r['period_id']),
                'size_result': str(r['size_result']),
                'color_result': str(r['color_result']),
                'created_at': r['created_at']
            } for r in res] if res else []
        except Exception as e:
            print(f"[PostgresDB Failover] calculate_hourly_profile failed: {e}. Switching to Excel.")
            use_postgres = False
            
    if not use_postgres:
        with excel_lock:
            try:
                df = load_preds()
                df_proc = df[df['is_processed'] == True]
                predictions_list = []
                for _, row in df_proc.iterrows():
                    predictions_list.append({
                        'period_id': str(row['period_id']),
                        'size_result': str(row['size_result']),
                        'color_result': str(row['color_result']),
                        'created_at': row['created_at']
                    })
            except Exception:
                predictions_list = []
                
    # Now group by hour of day (from 0 to 23)
    hourly_stats = {h: {"size_wins": 0, "color_wins": 0, "total": 0} for h in range(24)}
    
    for pred in predictions_list:
        try:
            created_str = pred.get('created_at')
            if created_str:
                hour = int(str(created_str).split()[1].split(':')[0])
            else:
                p_id = pred.get('period_id')
                hour = int(str(p_id)[8:10])
                
            if 0 <= hour < 24:
                hourly_stats[hour]["total"] += 1
                if pred.get("size_result") == "WIN":
                    hourly_stats[hour]["size_wins"] += 1
                if pred.get("color_result") == "WIN":
                    hourly_stats[hour]["color_wins"] += 1
        except Exception:
            continue
            
    profile = []
    for h in range(24):
        stats = hourly_stats[h]
        tot = stats["total"]
        size_pct = round((stats["size_wins"] / tot) * 100) if tot > 0 else 0
        color_pct = round((stats["color_wins"] / tot) * 100) if tot > 0 else 0
        
        avg_pct = (size_pct + color_pct) / 2.0
        if tot < 5:
            score = "CALIBRATING"
            color_theme = "#a855f7"
        elif avg_pct >= 72.0:
            score = "HIGH PROFIT"
            color_theme = "#06b6d4"
        elif avg_pct >= 58.0:
            score = "STABLE"
            color_theme = "#10b981"
        else:
            score = "VOLATILE"
            color_theme = "#f43f5e"
            
        profile.append({
            "hour": h,
            "display_time": f"{h:02d}:00",
            "size_wins": stats["size_wins"],
            "color_wins": stats["color_wins"],
            "total": tot,
            "size_accuracy": size_pct,
            "color_accuracy": color_pct,
            "score": score,
            "color_theme": color_theme
        })
        
    return profile

def restore_predictions_from_rounds():
    """Self-healing restoration: regenerates prediction outcomes from existing rounds data."""
    global use_postgres
    try:
        # Check if predictions are empty
        pred_count = 0
        if use_postgres:
            res = pg_execute("SELECT COUNT(*) as cnt FROM predictions;", fetch='one')
            pred_count = res['cnt'] if res else 0
        else:
            with excel_lock:
                try:
                    df_p = load_preds()
                    pred_count = len(df_p)
                except Exception:
                    pred_count = 0
                
        if pred_count > 10:
            print("[DataRestoration] Predictions table already has records. Skipping auto-restore.")
            return True
            
        print("[DataRestoration] Clean predictions table detected! Initiating prediction logs reconstruction...")
        
        # Load the rounds
        rounds = []
        if use_postgres:
            res = pg_execute("SELECT period_id, number, size, color FROM rounds ORDER BY period_id ASC;", fetch='all')
            rounds = res if res else []
        else:
            with excel_lock:
                try:
                    df_r = load_rounds()
                    rounds = df_r.to_dict('records')
                except Exception:
                    rounds = []
                
        if len(rounds) < 15:
            print("[DataRestoration] Insufficient rounds to reconstruct.")
            return True
            
        # Re-run ML predictions for each past round
        import brain
        # Make sure brain global is trained
        if not brain.global_brain.is_trained:
            brain.global_brain.train()
            
        restored_preds = []
        rounds_sorted = sorted(rounds, key=lambda x: int(x['period_id']))
        
        for idx in range(15, len(rounds_sorted)):
            target_round = rounds_sorted[idx]
            target_period = int(target_round['period_id'])
            
            prior_rounds = rounds_sorted[max(0, idx-30):idx]
            prior_rounds_desc = sorted(prior_rounds, key=lambda x: int(x['period_id']), reverse=True)
            
            res_ml = brain.global_brain.predict_next(prior_rounds_desc)
            if res_ml:
                pred_size = res_ml["ml_size"]
                pred_color = res_ml["ml_color"]
                size_conf = res_ml["ml_size_confidence"]
                color_conf = res_ml["ml_color_confidence"]
                
                actual_size = target_round['size']
                actual_color = target_round['color']
                
                size_res = "WIN" if str(pred_size).strip().lower() == str(actual_size).strip().lower() else "LOSS"
                color_res = "WIN" if str(pred_color).strip().lower() in str(actual_color).strip().lower() else "LOSS"
                
                # Approximate timestamp from period id
                p_str = str(target_period)
                ts_str = f"2026-05-20 {int(p_str[8:10]) % 24:02d}:00:00" if len(p_str) >= 10 else "2026-05-20 12:00:00"
                
                restored_preds.append({
                    "period_id": target_period,
                    "predicted_size": pred_size,
                    "predicted_color": pred_color,
                    "size_confidence": size_conf,
                    "color_confidence": color_conf,
                    "actual_size": actual_size,
                    "actual_color": actual_color,
                    "size_result": size_res,
                    "color_result": color_res,
                    "is_processed": True,
                    "created_at": ts_str
                })
                
        # Bulk save
        if len(restored_preds) > 0:
            if use_postgres:
                for rp in restored_preds:
                    pg_execute(
                        "INSERT INTO predictions (period_id, predicted_size, predicted_color, size_confidence, color_confidence, actual_size, actual_color, size_result, color_result, is_processed, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (period_id) DO NOTHING;",
                        (rp['period_id'], rp['predicted_size'], rp['predicted_color'], rp['size_confidence'], rp['color_confidence'], rp['actual_size'], rp['actual_color'], rp['size_result'], rp['color_result'], True, rp['created_at'])
                    )
            else:
                with excel_lock:
                    df_p = load_preds()
                    new_df = pd.DataFrame(restored_preds)
                    df_merged = pd.concat([df_p, new_df]).drop_duplicates(subset=['period_id'], keep='last')
                    save_preds(df_merged)
                    
            print(f"[DataRestoration Success] Reconstructed {len(restored_preds)} prediction logs cleanly!")
            db_cache.clear()
            
        return True
    except Exception as e:
        print(f"[DataRestoration Error] Reconstruct failed: {e}")
        return False

