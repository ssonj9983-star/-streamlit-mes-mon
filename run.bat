@echo off
chcp 65001 >nul
title MES/POP 실시간 모니터링 Dashboard

echo =============================================
echo  MES/POP 실시간 모니터링 Dashboard 시작 중...
echo  외부 접속 URL: http://ssonj11.tplinkdns.com:8502
echo  내부 접속 URL: http://localhost:8502
echo =============================================
echo.

cd /d "%~dp0"

REM 가상환경 활성화
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [경고] 가상환경(.venv)을 찾을 수 없습니다.
    echo pip install -r requirements.txt 를 먼저 실행하세요.
    pause
    exit /b 1
)

REM Streamlit 실행 (config.toml 설정에 따라 0.0.0.0:8502 로 바인딩)
streamlit run app.py

pause
