@echo off
chcp 65001 >nul
cd /d "%~dp0"
python rakip_takip.py >> "%~dp0log.txt" 2>&1
