@echo off
cd /d "C:\Users\SindreLøvlieHaugen\Documents\systemer\TriMCP"
:: Ensure databases are up
docker-compose up -d
:: Start SSE server
.venv\Scripts\python.exe sse_server.py
