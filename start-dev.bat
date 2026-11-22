@echo off
title Semantic Cache Engine - Dev Launcher
echo Starting PostgreSQL and Redis...
docker compose --env-file backend\.env up -d postgres redis

echo Starting Backend (FastAPI auto-reload on http://127.0.0.1:9417)...
start "SC Backend (9417)" cmd /k "cd /d %~dp0backend && python run.py"

echo Starting Frontend (Next.js Fast Refresh on http://localhost:3001)...
start "SC Frontend (3001)" cmd /k "cd /d %~dp0frontend && npx next dev -p 3001"

echo Both servers launched with auto-reload enabled!
