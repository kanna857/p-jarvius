@echo off
:: JARVIS Startup Script
:: Place a shortcut to this file in:
::   %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
:: That way JARVIS launches silently every time Windows starts.

:: Change this path to your actual JARVIS folder
:: Use the directory where the script is located
set JARVIS_DIR=%~dp0

:: Activate virtual environment if it exists
if exist "%JARVIS_DIR%\.venv\Scripts\activate.bat" (
    call "%JARVIS_DIR%\.venv\Scripts\activate.bat"
) else if exist "%JARVIS_DIR%\venv\Scripts\activate.bat" (
    call "%JARVIS_DIR%\venv\Scripts\activate.bat"
)

:: Run JARVIS Backend (silent)
cd /d "%JARVIS_DIR%"
if exist "%JARVIS_DIR%\.venv" (
    start "" "%JARVIS_DIR%\.venv\Scripts\pythonw.exe" jarvis_with_memory.py
) else if exist "%JARVIS_DIR%\venv" (
    start "" "%JARVIS_DIR%\venv\Scripts\pythonw.exe" jarvis_with_memory.py
) else (
    start "" pythonw jarvis_with_memory.py
)
