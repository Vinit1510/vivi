import os
import time
import requests
import threading
import traceback
import json
from datetime import datetime, timezone
import db

# Constants
WINGO_URL = "https://draw.ar-lottery01.com/WinGo/WinGo_30S/GetHistoryIssuePage.json"
INTERVAL = 1.5  # Poll every 1.5 seconds for ultra-low latency

def get_color(number):
    num = int(number)
    if num == 0: return "RedViolet"
    if num == 5: return "GreenViolet"
    if num in [1, 3, 7, 9]: return "Green"
    return "Red"

def get_size(number):
    return "Big" if int(number) >= 5 else "Small"

def fetch_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://draw.ar-lottery01.com/"
    }
    ts = int(time.time() * 1000)
    url = f"{WINGO_URL}?ts={ts}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return data.get("data", {}).get("list", []) or []
            elif isinstance(data, list):
                return data
        return []
    except Exception as e:
        print(f"❌ Miner Network Error: {e}")
        return []

def process_records(records):
    if not records:
        return 0
    
    saved_count = 0
    
    # Process oldest to newest
    for rec in reversed(records):
        try:
            period_id = int(rec.get("issueNumber"))
            num = int(rec.get("number"))
            size = get_size(num)
            color = get_color(num)
            raw = json.dumps(rec)
            
            # Insert into Excel database
            added = db.add_round(period_id, num, size, color, raw)
            if added:
                saved_count += 1
                # Update predictions
                db.update_prediction_outcomes(period_id, size, color)
                
        except Exception as ex:
            print(f"⚠️ Error inserting record: {ex}")
            continue
            
    return saved_count

def verify_active_prediction():
    """Ensures that if predictions are enabled, the system always holds a forecast for the upcoming period."""
    try:
        active_status = db.get_system_config('prediction_active', 'false')
        if active_status != 'true':
            return
            
        latest_id = db.get_latest_round_id()
        if latest_id == 0:
            return
        next_id = latest_id + 1
        
        # Check if database already houses a prediction for this forthcoming block
        if db.check_prediction_exists(next_id):
            return
            
        import brain
        forecast = brain.generate_forecast()
        if forecast.get("ml_size") == "WAIT":
            return
            
        db.add_prediction(
            next_id, 
            forecast.get("ml_size"), 
            forecast.get("ml_color"), 
            forecast.get("ml_size_confidence"), 
            forecast.get("ml_color_confidence")
        )
        print(f"🔮 Daemon Prediction successfully registered for Period {next_id}.")
    except Exception as e:
        print(f"⚠️ Autonomous prediction failure: {e}")


def start_miner_loop():
    print("🚀 Initializing Vivi 24/7 Miner (Excel Database Mode)...")
    
    last_processed_period_id = None
    
    while True:
        try:
            records = fetch_data()
            if records:
                latest_period = int(records[0].get("issueNumber"))
                
                # LAZY MINER BYPASS: If the latest drawn period has not changed, bypass disk completely!
                if latest_period == last_processed_period_id:
                    time.sleep(INTERVAL)
                    continue
                
                inserted = process_records(records)
                if inserted > 0:
                    print(f"📦 Data Ingested: Added {inserted} new rounds from Wingo.")
                
                # Ignite automatic prediction engine verification
                verify_active_prediction()
                
                last_processed_period_id = latest_period
            else:
                time.sleep(INTERVAL)
                continue
                
            time.sleep(INTERVAL)
            
        except KeyboardInterrupt:
            print("Stopping miner gracefully...")
            break
        except Exception as e:
            print(f"🔥 FATAL MINER LOOP EXCEPTION:")
            traceback.print_exc()
            time.sleep(10) # Wait longer before retrying after critical crash

def run_in_background():
    miner_thread = threading.Thread(target=start_miner_loop, daemon=True)
    miner_thread.start()
    print("⚡ Miner detached to background thread.")
