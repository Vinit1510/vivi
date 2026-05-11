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

# Startup lifecycle
@app.on_event("startup")
async def startup_event():
    print("--- 🚀 Starting VIVI Backend Node ---")
    db_mgr.connect()
    miner.run_in_background()
    print("VIVI System Fully Online.")

import os

# Root path serves Index.html
@app.get("/")
def get_dashboard():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    return FileResponse(frontend_path)

@app.get("/api/dashboard-stats")
def get_dashboard_stats():
    """Provides top-level overview stats."""
    try:
        total_rounds = execute_one("SELECT COUNT(*) FROM rounds;")[0]
        recent = fetch_all("SELECT * FROM rounds ORDER BY period_id DESC LIMIT 10")
        
        active_res = execute_one("SELECT value FROM system_config WHERE key = 'prediction_active'")
        is_active = active_res[0] == 'true' if active_res else False
        
        # Calculate accuracy for size and color
        acc_res = fetch_all("""
            SELECT 
                COUNT(*) filter (WHERE size_result = 'WIN') as size_wins,
                COUNT(*) filter (WHERE color_result = 'WIN') as color_wins,
                COUNT(*) filter (WHERE is_processed = TRUE) as total_preds
            FROM predictions
        """)
        
        stats = acc_res[0] if acc_res else {"size_wins":0, "color_wins":0, "total_preds":0}
        
        return {
            "total_ingested": total_rounds,
            "prediction_enabled": is_active,
            "recent_rounds": recent,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/available-dates")
def get_available_dates():
    """Returns sorted list of dates with data."""
    try:
        res = fetch_all("""
            SELECT DISTINCT DATE_TRUNC('day', created_at AT TIME ZONE 'UTC')::date as valid_date 
            FROM rounds 
            ORDER BY valid_date DESC 
            LIMIT 30;
        """)
        return [str(r["valid_date"]) for r in res]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history/date/{target_date}")
def get_date_details(target_date: str):
    """Retrieves nested hierarchical JSON (Hour -> Rounds) for filtering."""
    try:
        # SQL to group by hour efficiently
        query = """
            SELECT 
                EXTRACT(HOUR FROM created_at) as hour,
                COUNT(*) as count,
                JSON_AGG(
                    JSON_BUILD_OBJECT(
                        'period_id', period_id,
                        'number', number,
                        'size', size,
                        'color', color,
                        'time', created_at::time
                    ) ORDER BY period_id DESC
                ) as rounds
            FROM rounds
            WHERE created_at::date = %s
            GROUP BY EXTRACT(HOUR FROM created_at)
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
