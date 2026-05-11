@echo off
title VIVI PREDICTIVE ENGINE
echo ==============================================
echo 🚀 VIVI ENGINE - IGNITION IN PROGRESS
echo ==============================================
echo.
cd backend
echo [1/2] Activating Virtual Environment...
call .venv\Scripts\activate
echo.
echo [2/2] Starting Python FastAPI Server on Port 8000...
echo.
python server.py
pause
