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
        forecast = {
            "ml_size": "WAIT", "ml_color": "TRAINING", "ml_size_confidence": 0.0, "ml_color_confidence": 0.0,
            "heu_size": "WAIT", "heu_color": "TRAINING", "heu_size_confidence": 0.0, "heu_color_confidence": 0.0
        }
        if is_active and next_id != "PENDING":
            saved_pred = db.get_prediction(next_id)
            
            # Fetch the latest round to compute heuristic dynamically
            all_data = db.get_latest_rounds(1)
            latest_num = int(all_data[0]['number']) if all_data else 0
            size_heuristic = "Small" if latest_num >= 5 else "Big"
            color_heuristic = "Red" if latest_num in [0, 2, 4, 6, 8] else "Green"
            
            if saved_pred:
                forecast = {
                    "ml_size": saved_pred["predicted_size"] or "WAIT",
                    "ml_color": saved_pred["predicted_color"] or "WAIT",
                    "ml_size_confidence": saved_pred["size_confidence"] or 0.0,
                    "ml_color_confidence": saved_pred["color_confidence"] or 0.0,
                    "heu_size": size_heuristic,
                    "heu_color": color_heuristic,
                    "heu_size_confidence": 58.4,
                    "heu_color_confidence": 56.2
                }
            else:
                # Fallback: Background miner hasn't cycled yet, compute dynamic forecast
                forecast = brain.generate_forecast()
                # Instantly persist fallback to ensure continuity
                if forecast["ml_size"] != "WAIT":
                     db.add_prediction(
                         next_id, 
                         forecast["ml_size"], 
                         forecast["ml_color"], 
                         forecast["ml_size_confidence"], 
                         forecast["ml_color_confidence"]
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

@app.get("/api/scalper-stats")
def get_scalper_stats():
    """Calculates live 10-Period Scalper forecasts and backtests on the last 15 rounds."""
    try:
        # Fetch latest 26 rounds to compute sliding window history of 15 rounds
        all_data = db.get_latest_rounds(26)
        if not all_data or len(all_data) < 12:
            return {"next_forecast": None, "history": []}
            
        # 1. Compute next forthcoming round forecast
        next_forecast = brain.predict_scalper_10(all_data[:10])
        
        # Calculate Wingo's actual next period ID
        latest_period_id = int(all_data[0].get("period_id"))
        next_period = str(latest_period_id + 1)
        
        # 2. Backtest last 15 rounds using preceding 10-period sliding window
        history_list = []
        limit = min(15, len(all_data) - 11)
        for i in range(limit):
            target_round = all_data[i]
            # Preceding 10 rounds relative to target_round
            preceding_10 = all_data[i+1 : i+11]
            
            # Predict
            pred = brain.predict_scalper_10(preceding_10)
            
            # Compare actual outcomes
            actual_size = target_round.get("size")
            actual_color = target_round.get("color")
            
            pred_size = pred.get("size")
            pred_color = pred.get("color")
            
            size_result = "WIN" if str(actual_size).strip().lower() == str(pred_size).strip().lower() else "LOSS"
            color_result = "WIN" if str(actual_color).strip().lower() == str(pred_color).strip().lower() else "LOSS"
            
            history_list.append({
                "period_id": target_round.get("period_id"),
                "number": target_round.get("number"),
                "actual_size": actual_size,
                "pred_size": pred_size,
                "size_result": size_result,
                "actual_color": actual_color,
                "pred_color": pred_color,
                "color_result": color_result,
                "size_confidence": pred.get("size_confidence"),
                "color_confidence": pred.get("color_confidence")
            })
            
        return {
            "next_period": next_period,
            "next_forecast": next_forecast,
            "history": history_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Mount entire frontend folder to serve static assets (style.css, app.js) directly at root

app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend")), name="frontend")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
