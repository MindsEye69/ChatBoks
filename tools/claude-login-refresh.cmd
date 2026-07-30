@echo off
setlocal

title ChatBoks Claude Login Refresh
cd /d "%~dp0\.."

if /I "%~1"=="--check" goto check

echo ChatBoks Claude Login Refresh
echo.
echo This runs Claude Code's supported auth refresh flow:
echo.
echo   claude auth login --claudeai
echo.
echo Complete any browser or terminal login prompt Claude opens.
echo This window will then test the external Claude mode that ChatBoks uses.
echo.
pause

where claude >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERROR: claude was not found on PATH.
    echo Install Claude Code or repair PATH, then run this again.
    echo.
    pause
    exit /b 1
)

claude auth login --claudeai

:check
echo.
echo Checking Claude auth status...
claude auth status
echo.
echo Testing Claude external prompt mode...
echo Reply with OK only. | claude --print --dangerously-skip-permissions
if errorlevel 1 (
    echo.
    echo Claude external prompt mode is still not authenticated.
    echo Run this launcher again and complete /login inside Claude.
    echo.
    if /I not "%~1"=="--check" pause
    exit /b 1
)

echo.
echo Claude external prompt mode is working.
echo.
if /I not "%~1"=="--check" pause
exit /b 0
