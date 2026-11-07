@echo off
REM Запуск агента "Гостевой режим ПК" из терминала.
REM Можно вызывать откуда угодно: start "" "путь\к\guest_mode\agent\start_agent.bat"
cd /d "%~dp0"
python agent.py
pause
