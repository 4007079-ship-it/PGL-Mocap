@echo off
chcp 65001 >nul
rem Запуск PGL Mocap из исходников (без сборки exe). Нужен один раз запущенный build.bat
rem или вручную созданное окружение .venv с зависимостями из requirements.txt.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Сначала запустите build.bat — он создаст окружение .venv
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" run_pgl_mocap.py
