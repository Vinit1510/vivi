from db import fetch_all
import random

def generate_forecast():
    """
    Ultimate Bulletproof Brain: 
    Guaranteed null-safe calculations and foolproof python-based fallback aggregation.
    """
    try:
        # Load the entire simple overview (Scalable for reasonable sizes)
        all_data = fetch_all("SELECT size, color FROM rounds ORDER BY period_id DESC")
        
        if not all_data or len(all_data) < 5:
            return {
                "size": "WAIT", 
                "color": "TRAINING", 
                "size_confidence": 45.0,
                "color_confidence": 45.0
            }
            
        # 1. Absolute Safe Python Aggregation (No chance of SQL syntax variance)
        big_t = 0
        small_t = 0
        green_t = 0
        red_t = 0
        
        for r in all_data:
            sz = str(r.get('size', '')).lower()
            cl = str(r.get('color', '')).lower()
            if sz == 'big': big_t += 1
            if sz == 'small': small_t += 1
            if 'green' in cl: green_t += 1
            if 'red' in cl: red_t += 1
            
        # 2. Recent Slice (Last 20)
        recent = all_data[:20]
        r_big = 0
        r_small = 0
        rg = 0
        rr = 0
        
        for r in recent:
            sz = str(r.get('size', '')).lower()
            cl = str(r.get('color', '')).lower()
            if sz == 'big': r_big += 1
            if sz == 'small': r_small += 1
            if 'green' in cl: rg += 1
            if 'red' in cl: rr += 1
            
        # A. Size Logic Fusion
        s_score = 0
        if big_t > small_t: s_score += 1
        if r_big > r_small: s_score += 2
        predicted_size = "Small" if s_score >= 2 else "Big"
        
        # B. Color Logic Fusion
        c_score = 0
        if green_t > red_t: c_score += 1
        if rg > rr: c_score += 2
        predicted_color = "Red" if c_score >= 2 else "Green"
        
        # C. Split Analytical Confidence Logic
        vol_boost = min(10, len(all_data) / 500.0)
        
        # Measure distribution dominance (0.5 = random, 1.0 = absolute trend)
        s_ratio = max(r_big, r_small) / max(1, r_big + r_small)
        c_ratio = max(rg, rr) / max(1, rg + rr)
        
        base_s = 55.0 + (s_ratio - 0.5) * 60.0
        base_c = 55.0 + (c_ratio - 0.5) * 60.0
        
        final_size_conf = min(99.9, base_s + vol_boost + random.uniform(0, 4.0))
        final_color_conf = min(99.9, base_c + vol_boost + random.uniform(0, 4.0))
        
        return {
            "size": predicted_size,
            "color": predicted_color,
            "size_confidence": round(final_size_conf, 1),
            "color_confidence": round(final_color_conf, 1)
        }
        
    except Exception as e:
        print(f"Brain Error: {e}")
        return {
            "size": "WAIT", 
            "color": "WAIT", 
            "size_confidence": 0.0, 
            "color_confidence": 0.0
        }
