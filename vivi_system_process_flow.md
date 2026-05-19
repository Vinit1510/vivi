# 🔱 VIVI SYSTEM PROCESS FLOW BLUEPRINT

Welcome to the definitive architectural blueprint of the upgraded, hyper-resilient **VIVI Analytics Engine**. This document maps out the system's entire data pipeline, machine learning loop, and self-healing hybrid database engine.

---

## 🗺️ High-Level System Architecture (Step-by-Step Arrow Flow)

Here is the exact step-by-step process flow of VIVI, mapped with sequential arrows for maximum clarity:

```text
🔄 1. REAL-TIME WINGO MINER LOOP:
[Wingo 30S API] ➡️ Polls every 1.5s ➡️ [Check: New Period?]
                                            ├── ❌ No  ➡️ Sleep & Poll again
                                            └── ✅ Yes ➡️ [Fetch Last 10 Rounds]

📥 2. DATA INGESTION & DE-DUPLICATION:
[Last 10 Rounds] ➡️ Strictly parse 17-digit Period IDs (Strings) ➡️ [Check: Duplicate?]
                                                                          ├── ❌ Yes ➡️ Ignore / Skip
                                                                          └── ✅ No  ➡️ [Prepare Database Entry]

🛡️ 3. HYBRID DATABASE ROUTING (SELF-HEALING):
[Save Record] ➡️ [Check: DATABASE_URL present?]
                      ├── ❌ No (Local) ➡️ [Save to EXTRACTED/rounds.xlsx]
                      └── ✅ Yes (Neon) ➡️ [Attempt Postgres Connection]
                                                 ├── ❌ Fail (Quota/Auth) ➡️ Fallback ➡️ [Save to Excel]
                                                 └── ✅ Pass ➡️ [Check: DB Empty?]
                                                                    ├── ✅ Yes ➡️ [Seeder: Sync 20,012 rounds] ➡️ [Save to Neon SQL]
                                                                    └── ❌ No  ➡️ [Save to Neon SQL]

🧠 4. MACHINE LEARNING TRAINING LOOP:
[Saved Rounds] ➡️ Trigger ML Training ➡️ Load historical dataset (Excel or SQL)
                                                 ➡️ Filter out NaN & format Period IDs
                                                 ➡️ Construct 3-period rolling lag vectors
                                                 ➡️ Train High-Performance Random Forest
                                                 ➡️ [Model Saved in memory]

🔮 5. FORECAST & OUTCOME EVALUATION:
[Model in memory] ➡️ Generate prediction for next Period (e.g. 20260519100050343)
                      ➡️ Predict Size (Big/Small) & Color (Red/Green)
                      ➡️ Wait for Wingo Miner to fetch next completed period
                      ➡️ Compare actual draw outcome vs predicted forecast
                      ➡️ Calculate Win/Loss stats ➡️ [Serve to FastAPI & Dashboard UI 📈]
```

---

## 🗺️ High-Level Mermaid Architecture


This flowchart visualizes the complete process flow, from raw real-time Wingo data extraction to AI-driven predictions and our dynamic self-healing database failover mechanism.

```mermaid
graph TD
    %% Styling
    classDef main fill:#2C3E50,stroke:#34495E,stroke-width:2px,color:#ECF0F1;
    classDef db fill:#27AE60,stroke:#2ECC71,stroke-width:2px,color:#ECF0F1;
    classDef ml fill:#8E44AD,stroke:#9B59B6,stroke-width:2px,color:#ECF0F1;
    classDef fail fill:#C0392B,stroke:#E74C3C,stroke-width:2px,color:#ECF0F1;

    %% 1. Ingestion Pipeline
    A["Wingo API Polling<br>(miner.py every 1.5s)"] --> B{"Latest Period Changed?"}
    B -- "No (Lazy Miner)" --> A
    B -- "Yes" --> C["Fetch 10 Historical Records"]

    %% 2. Hybrid Data Storage & Self-Healing Failover
    C --> D{"DATABASE_URL Set?"}
    D -- "No" --> E["Excel Mode<br>(EXTRACTED/rounds.xlsx)"]::db
    D -- "Yes" --> F["Attempt Neon Postgres Connection"]::db
    F -- "Success" --> G{"Neon Table Empty?"}::db
    F -- "Failure (Quota/Auth)" --> H["Instantly Fallback to Excel"]::fail
    H --> E
    
    G -- "Yes" --> I["Run One-Click Seeder<br>(Sync 20,012 historical rows)"]::db
    G -- "No" --> J["Regular Postgres Mode"]::db
    I --> J
    J --> K["Batch Upsert Records & Outcomes"]::db

    %% 3. Machine Learning Forecasting
    K --> L["Trigger ML Training Loop<br>(brain.py)"]::ml
    E --> L
    L --> M["Load Dataset (SQL or Excel)"]::ml
    M --> N["Deduplicate & Parse Strict 17-digit Period IDs"]::ml
    N --> O["Construct Lag Features & Targets"]::ml
    O --> P["Fit Random Forest Classifiers"]::ml
    P --> Q["Persist Model in Memory"]::ml

    %% 4. Execution / Prediction Output
    Q --> R["Generate Live Forecast for Period + 1"]::ml
    R --> S["Upsert Prediction Row"]
    S --> T["FastAPI Web Dashboard UI"]::main
    
    class A,B,C,S,T main;
    class E,F,G,I,J,K db;
    class L,M,N,O,P,Q,R ml;
    class H fail;
```

---

## ⚙️ Core Process Flows Explained

### 🔄 1. The Real-Time Data Miner Pipeline (`miner.py`)
1. **Ultra-low latency Polling**: The background thread polls the Wingo API every **1.5 seconds**.
2. **Lazy Miner Optimization**: The miner compares the latest drawn ID in memory. If no new block has completed, **it skips disk operations completely**, saving CPU and database IOPS.
3. **Ingestion & Resolution**: When a new block is detected, Wingo's last 10 rounds are retrieved. VIVI parses the results, updates predictions for completed periods, and registers outcomes.

---

### 🛡️ 2. The Dynamic Self-Healing Hybrid DB (`db.py`)
Every database call is now protected by a dynamic, runtime failover wrapper:
```python
# Conceptual Flow of EVERY database query in db.py:
def execute_db_operation():
    if use_postgres:
        try:
            # 1. Attempt PostgreSQL connection & query execution
            return pg_execute("...")
        except Exception as e:
            # 2. Catch failures (quota, timeouts, password changes)
            print("[Failover] Postgres offline. Switching to Excel.")
            use_postgres = False
            
    # 3. Seamlessly execute offline Local Excel file fallback
    return local_excel_execute()
```
* **Seeder Mechanism**: When a clean PostgreSQL database is connected, VIVI automatically checks if it contains 0 rounds. If empty, it instantly streams the entire local dataset (all **20,012 pristine historical consecutive rounds**) into Postgres in high-speed batches.

---

### 🧠 3. Machine Learning brain (`brain.py`)
* **Strict Strings Only**: To prevent python/numpy from treating the 17-digit `period_id` (e.g., `20260519100050337`) as floating-point scientific notation and truncating data, it is processed, sorted, and matched strictly as strings.
* **Feature Engineering**: Constructs 3-period lag vectors (historical features) to train the **Random Forest Classifiers**.
* **Rolling ML predictions**: Fits models on all available records, optimizes hyperparameters, and generates confidence-rated forecasts for the upcoming active Wingo period.

---

### 🌐 4. Web Service and Caching (`server.py`)
* **API Endpoints**: Serves FastAPI endpoints (`/api/dashboard-stats`, `/api/available-dates`, `/api/history/...`) to fetch stats and stats charts.
* **Transient Cache**: Holds a thread-safe, in-memory cache layer to buffer incoming frontend request storms, preserving your system's performance.
