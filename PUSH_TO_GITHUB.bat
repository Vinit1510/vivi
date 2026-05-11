@echo off
title VIVI GITHUB SYNC
echo =================================================
echo 🐙 PREPARING SOURCE DELIVERY TO GITHUB
echo =================================================
echo.
echo [1/3] Staging changes...
git add .
echo.
echo [2/3] Committing snapshot...
set /p commit_msg="Enter commit description (Default: Auto-update): "
if "%commit_msg%"=="" set commit_msg="Auto-update VIVI system"
git commit -m "%commit_msg%"
echo.
echo [3/3] Pushing to Github repository (main branch)...
git push origin main --force
echo.
echo =================================================
echo ✅ DELIVERY COMPLETED
echo =================================================
pause
