import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

import db
import miner
import brain

app = FastAPI(title="Vivi Analytics Engine API (Excel DB Mode)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup lifecycle
@app.on_event("startup")
def startup_event():
    print("--- 🚀 Starting VIVI Backend Node (Excel DB Mode) ---")
    miner.run_in_background()
    print("VIVI System Fully Online.")

# Root path serves Index.html
@app.get("/")
@app.head("/")
def get_dashboard():
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    return FileResponse(frontend_path)

# ==========================================================================
# TRANSIENT THREAD-SAFE IN-MEMORY CACHE FOR EXCEL DB BANDWIDTH OPTIMIZATION
# ==========================================================================
class CacheStore:
    def __init__(self):
        self.dashboard_stats = None
        self.stats_time = 0
        self.available_dates = None
        self.dates_time = 0
        self.history_cache = {}  # target_date -> (timestamp, data)

cache = CacheStore()

@app.get("/api/dashboard-stats")
def get_dashboard_stats():
    """Provides top-level overview stats and immediate next forecast with in-memory caching."""
    now = time.time()
    # Cache stats for 4 seconds (effectively bypasses frontend request storms)
    if cache.dashboard_stats and (now - cache.stats_time < 4.0):
        return cache.dashboard_stats
        
    try:
        total_rounds = db.get_total_rounds_count()
        latest_id = db.get_latest_round_id()
        next_id = latest_id + 1 if latest_id > 0 else "PENDING"
        
        active_status = db.get_system_config('prediction_active', 'false')
        is_active = (active_status == 'true')
        
        # Get current brain analysis (Fetch pre-computed background forecast if exists)
        forecast = {"size": "WAIT", "color": "TRAINING", "size_confidence": 0.0, "color_confidence": 0.0}
        if is_active and next_id != "PENDING":
            saved_pred = db.get_prediction(next_id)
            if saved_pred:
                forecast = {
                    "size": saved_pred["predicted_size"] or "WAIT",
                    "color": saved_pred["predicted_color"] or "WAIT",
                    "size_confidence": saved_pred["size_confidence"] or 0.0,
                    "color_confidence": saved_pred["color_confidence"] or 0.0
                }
            else:
                # Fallback: Background miner hasn't cycled yet, compute dynamic forecast
                forecast = brain.generate_forecast()
                # Instantly persist fallback to ensure continuity
                if forecast["size"] != "WAIT":
                     db.add_prediction(
                         next_id, 
                         forecast["size"], 
                         forecast["color"], 
                         forecast["size_confidence"], 
                         forecast["color_confidence"]
                     )
        
        stats = db.get_accuracy_stats()
        
        res_data = {
            "total_ingested": total_rounds,
            "prediction_enabled": is_active,
            "next_period": str(next_id),
            "forecast": forecast,
            "stats": stats
        }
        cache.dashboard_stats = res_data
        cache.stats_time = now
        return res_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/available-dates")
def get_available_dates():
    """Returns sorted list of dates with data with 30-sec cache buffer."""
    now = time.time()
    if cache.available_dates and (now - cache.dates_time < 30.0):
        return cache.available_dates
        
    try:
        res_dates = db.get_available_dates()
        cache.available_dates = res_dates
        cache.dates_time = now
        return res_dates
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history/date/{target_date}")
def get_date_details(target_date: str):
    """Retrieves nested hierarchical JSON grouped by IST hours with 8-sec cache."""
    now = time.time()
    cached_entry = cache.history_cache.get(target_date)
    if cached_entry and (now - cached_entry[0] < 8.0):
        return cached_entry[1]
        
    try:
        results = db.get_hourly_history(target_date)
        cache.history_cache[target_date] = (now, results)
        return results
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/prediction/toggle")
def toggle_prediction(status: bool):
    try:
        val_str = 'true' if status else 'false'
        db.set_system_config('prediction_active', val_str)
        
        # Force cache invalidation immediately on state change!
        cache.dashboard_stats = None
        
        return {"success": True, "prediction_active": status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount entire frontend folder to serve static assets (style.css, app.js) directly at root
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend")), name="frontend")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
