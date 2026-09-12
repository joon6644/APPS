@echo off
rem ---------------------------------------------------------------
rem  AI Debate Judge launcher
rem
rem  This file is intentionally ASCII-only. cmd.exe parses batch
rem  files using the OEM codepage, so Korean text inside a .bat
rem  gets split into broken commands. All user-facing messages
rem  live in run.ps1, which handles UTF-8 correctly.
rem ---------------------------------------------------------------

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"

if errorlevel 1 (
    echo.
    pause
)

rem cd C:\Workspace\APPS\debate_agent
rem C:\Workspace\APPS\.venv\Scripts\streamlit.exe run app.py
