@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Rakip Fiyat Takip Botu
echo ==========================================
echo   Rakip Fiyat Takip Botu
echo ==========================================
echo   Arayuz aciliyor...
echo.
python gui.py
if errorlevel 1 (
    echo.
    echo [HATA] Arayiz acilamadi.
    echo        Paketleri kurun:  pip install -r requirements.txt
    echo.
    pause
)
