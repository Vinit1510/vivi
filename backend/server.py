from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional, List
from datetime import datetime
import uvicorn

from db import db_mgr, fetch_all, execute_one
import miner

app = FastAPI(title="Vivi Analytics Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup lifecycle with auto-table creation
@app.on_event("startup")
async def startup_event():
    print("--- 🚀 Starting VIVI Backend Node ---")
    
    # 1. Initialize DB Pool
    db_mgr.connect()
    
    # 2. Auto-Execute Schema to prevent "Relation missing" errors
    try:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        if os.path.exists(schema_path):
            print("🛠️ Verifying database schema and patching constraints...")
            with open(schema_path, 'r') as f:
                sql = f.read()
            execute_one(sql)
            
            # REPAIR / MAINTENANCE: Ensure uniqueness in case of faulty manual initial create
            maintenance_sql = """
                -- 1. Upgrade column type to force absolute timezone storage if not already
                DO $$
                BEGIN
                    ALTER TABLE rounds ALTER COLUMN created_at TYPE TIMESTAMPTZ;
                EXCEPTION WHEN OTHERS THEN
                    NULL;
                END $$;

                -- 2. Delete physical duplicates keeping highest ID
                DELETE FROM rounds a USING (
                    SELECT MIN(id) as keep_id, period_id 
                    FROM rounds 
                    GROUP BY period_id HAVING COUNT(*) > 1
                ) b
                WHERE a.period_id = b.period_id AND a.id != b.keep_id;

                -- 3. Force add UNIQUE constraint safely if it didn't bind correctly
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_rounds_period') THEN
                        ALTER TABLE rounds ADD CONSTRAINT uq_rounds_period UNIQUE (period_id);
                    END IF;
                EXCEPTION WHEN OTHERS THEN 
                    NULL; 
                END $$;
            """
            execute_one(maintenance_sql)
            print("✅ Database structural integrity verified & healed.")
    except Exception as schema_err:
        print(f"⚠️ Warn during auto-schema: {schema_err}")

    # 3. Ignite autonomous miner
    miner.run_in_background()
    print("VIVI System Fully Online.")

import os

# Root path serves Index.html
@app.get("/")
def get_dashboard():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    return FileResponse(frontend_path)

import brain

@app.get("/api/dashboard-stats")
def get_dashboard_stats():
    """Provides top-level overview stats and immediate next forecast."""
    try:
        total_rounds_res = execute_one("SELECT COUNT(*) FROM rounds;")
        total_rounds = total_rounds_res[0] if total_rounds_res else 0
        
        recent = fetch_all("SELECT period_id FROM rounds ORDER BY period_id DESC LIMIT 1")
        latest_id = recent[0]["period_id"] if recent else 0
        next_id = latest_id + 1 if latest_id > 0 else "PENDING"
        
        active_res = execute_one("SELECT value FROM system_config WHERE key = 'prediction_active'")
        is_active = active_res[0] == 'true' if active_res else False
        
        # Get current brain analysis
        forecast = {"size": "WAIT", "color": "TRAINING", "confidence": 0}
        if is_active:
            forecast = brain.generate_forecast()
        
        # Calculate accuracy for size and color
        acc_res = fetch_all("""
            SELECT 
                COUNT(*) filter (WHERE size_result = 'WIN') as size_wins,
                COUNT(*) filter (WHERE color_result = 'WIN') as color_wins,
                COUNT(*) filter (WHERE is_processed = TRUE) as total_preds
            FROM predictions
        """)
        
        stats = acc_res[0] if (acc_res and acc_res[0]["total_preds"] is not None) else {"size_wins":0, "color_wins":0, "total_preds":0}
        
        return {
            "total_ingested": total_rounds,
            "prediction_enabled": is_active,
            "next_period": str(next_id),
            "forecast": forecast,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/available-dates")
def get_available_dates():
    """Returns sorted list of dates with data, casted to IST."""
    try:
        res = fetch_all("""
            SELECT DISTINCT DATE_TRUNC('day', created_at AT TIME ZONE 'Asia/Kolkata')::date as valid_date 
            FROM rounds 
            ORDER BY valid_date DESC 
            LIMIT 30;
        """)
        return [str(r["valid_date"]) for r in res]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history/date/{target_date}")
def get_date_details(target_date: str):
    """Retrieves nested hierarchical JSON grouped by Indian Time hours including outcome tracking."""
    try:
        query = """
            WITH ist_rounds AS (
                SELECT 
                    r.period_id, r.number, r.size, r.color, 
                    r.created_at AT TIME ZONE 'Asia/Kolkata' as local_time,
                    p.predicted_size, p.predicted_color,
                    p.size_result, p.color_result
                FROM rounds r
                LEFT JOIN predictions p ON r.period_id = p.period_id
            )
            SELECT 
                EXTRACT(HOUR FROM local_time) as hour,
                COUNT(*) as count,
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
                        'r_color', color_result
                    ) ORDER BY period_id DESC
                ) as rounds
            FROM ist_rounds
            WHERE local_time::date = %s
            GROUP BY EXTRACT(HOUR FROM local_time)
            ORDER BY hour DESC;
        """
        results = fetch_all(query, (target_date,))
        return results
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prediction/toggle")
def toggle_prediction(status: bool):
    try:
        val_str = 'true' if status else 'false'
        execute_one("""
            INSERT INTO system_config (key, value, updated_at)
            VALUES ('prediction_active', %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
        """, (val_str,))
        return {"success": True, "prediction_active": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount entire frontend folder to serve static assets (style.css, app.js) directly at root
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend")), name="frontend")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
