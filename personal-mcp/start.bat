@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Telegram MCP

rem ---- 1. Python ------------------------------------------------------------
set "PY=py -3"
%PY% --version >nul 2>&1 && goto have_python
set "PY=python"
%PY% --version >nul 2>&1 && goto have_python

echo Python не найден. Пробую установить через winget...
winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
echo.
echo Если установка прошла успешно - закройте это окно и запустите start.bat ещё раз.
echo Если нет - скачайте Python 3.10+ с https://www.python.org/downloads/
echo  и при установке отметьте "Add python.exe to PATH".
pause
exit /b 1

:have_python
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo Нужен Python 3.10 или новее. Обновите Python: https://www.python.org/downloads/
    pause
    exit /b 1
)

rem ---- 2. venv + зависимости ------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Создаю виртуальное окружение...
    %PY% -m venv .venv || goto fail
)
set "VPY=%~dp0.venv\Scripts\python.exe"
echo Проверяю зависимости...
"%VPY%" -m pip install -q --disable-pip-version-check -r requirements.txt || goto fail

rem ---- 3. Вход и регистрация ------------------------------------------------
set "ARG="
if /i "%~1"=="relogin"  set "ARG=--relogin"
if /i "%~1"=="register" set "ARG=--register"
if /i "%~1"=="test"     set "ARG=--test"
"%VPY%" login.py %ARG% || goto fail

echo.
echo Готово.
pause
exit /b 0

:fail
echo.
echo Что-то пошло не так - см. сообщения выше.
pause
exit /b 1
