@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem ============================================================
rem   Сборка плагина PGL Mocap Live Link под ваш Unreal Engine
rem   Нужно: Unreal Engine 5.6+ и Visual Studio 2022 с компонентом
rem   "Разработка игр на C++" (Game development with C++).
rem ============================================================
cd /d "%~dp0"

set "UE_ROOT=%~1"
if not defined UE_ROOT (
    for %%V in (5.8 5.7 5.6) do (
        if not defined UE_ROOT if exist "C:\Program Files\Epic Games\UE_%%V\Engine\Build\BatchFiles\RunUAT.bat" set "UE_ROOT=C:\Program Files\Epic Games\UE_%%V"
    )
)
if not defined UE_ROOT (
    echo Не нашёл Unreal Engine. Укажите путь к нему, например:
    echo   build_plugin.bat "D:\Epic Games\UE_5.6"
    pause
    exit /b 1
)
echo Unreal Engine: %UE_ROOT%

set "OUT=%~dp0Build\PGLMocapLiveLink"
if exist "%OUT%" rmdir /s /q "%OUT%"

call "%UE_ROOT%\Engine\Build\BatchFiles\RunUAT.bat" BuildPlugin ^
    -Plugin="%~dp0PGLMocapLiveLink\PGLMocapLiveLink.uplugin" ^
    -Package="%OUT%" ^
    -TargetPlatforms=Win64 -Rocket
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Плагин не собрался. Пришлите текст ошибки выше.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Готово: %OUT%
echo   Скопируйте папку PGLMocapLiveLink в папку Plugins вашего
echo   проекта (создайте Plugins рядом с .uproject, если её нет)
echo   и откройте проект.
echo ============================================================
pause
