@echo off
cd /d "%~dp0backend"
echo Starting SQLGen MCP Server...
.\venv\Scripts\python.exe mcp_server.py
pause
