@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo   PGL Mocap - сборка exe
echo ============================================
echo.

rem ---------- 1. Python (3.11 - 3.13) ----------
set "PY="
for %%V in (3.11 3.12 3.13) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<=(3,13) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo Python 3.11 не найден. Пробую установить через winget...
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
)
if not defined PY (
    echo.
    echo [ОШИБКА] Нужен Python 3.11 ^(или 3.12/3.13^).
    echo Скачайте с https://www.python.org/downloads/windows/ и при установке
    echo отметьте "Add python.exe to PATH". Затем запустите build.bat снова.
    pause
    exit /b 1
)
echo Использую: %PY%

rem ---------- 2. Виртуальное окружение и зависимости ----------
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv || goto :fail
)
set "VPY=.venv\Scripts\python.exe"
"%VPY%" -m pip install --upgrade pip || goto :fail
"%VPY%" -m pip install -r requirements.txt pyinstaller==6.22.3 || goto :fail

rem ---------- 3. Модели MediaPipe ----------
if not exist models mkdir models
set "MURL=https://storage.googleapis.com/mediapipe-models/pose_landmarker"
for %%M in (lite full heavy) do (
    if not exist "models\pose_landmarker_%%M.task" (
        echo Скачиваю модель %%M...
        curl.exe -L --fail -o "models\pose_landmarker_%%M.task" "%MURL%/pose_landmarker_%%M/float16/latest/pose_landmarker_%%M.task" || goto :fail
    )
)

rem ---------- 4. Сборка ----------
"%VPY%" -m PyInstaller --noconfirm --clean --windowed ^
    --name "PGL Mocap" ^
    --icon "assets\pgl_mocap.ico" ^
    --add-data "models;models" ^
    --add-data "assets;assets" ^
    --collect-all mediapipe ^
    --collect-all cyndilib ^
    --collect-submodules pygrabber ^
    --collect-submodules comtypes ^
    --hidden-import selftest ^
    run_pgl_mocap.py || goto :fail

copy /y "README.md" "dist\PGL Mocap\README.md" >nul

rem ---------- 5. Самопроверка собранного exe ----------
echo.
echo Самопроверка...
"dist\PGL Mocap\PGL Mocap.exe" --selftest
type "dist\PGL Mocap\pgl_mocap_selftest.txt"

rem ---------- 6. Архив ----------
if exist "dist\PGL_Mocap_win64.zip" del "dist\PGL_Mocap_win64.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\PGL Mocap' -DestinationPath 'dist\PGL_Mocap_win64.zip'"

echo.
echo ============================================
echo   Готово!
echo   Программа:  dist\PGL Mocap\PGL Mocap.exe
echo   Архив:      dist\PGL_Mocap_win64.zip
echo ============================================
pause
exit /b 0

:fail
echo.
echo [ОШИБКА] Сборка прервана. Смотрите сообщения выше.
pause
exit /b 1
