@echo off
REM ============================================
REM  삐삐 (Pager Simulator) EXE 빌드 스크립트
REM ============================================
REM  사용법: build.bat
REM  결과물: dist\pager.exe
REM ============================================

echo === 삐삐 EXE 빌드 시작 ===

C:\Users\c\AppData\Local\Programs\Python\Python311\Scripts\pyinstaller.exe ^
    --onefile ^
    --noconsole ^
    --name "pager" ^
    --icon NONE ^
    --add-data "neodgm.ttf;." ^
    --add-data "beep.wav;." ^
    --add-data "calendar_sync.py;." ^
    --hidden-import calendar_sync ^
    pager.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo === 빌드 성공! ===
    echo  EXE 위치: dist\pager.exe
    echo.
    echo  배포 시 exe 옆에 아래 파일을 함께 두세요:
    echo    - messages.json  (메시지 데이터)
    echo    - config.json    (캘린더 URL 설정, 선택사항)
    echo.

    REM dist 폴더에 messages.json 복사
    copy /Y messages.json dist\messages.json >nul 2>&1
    echo  messages.json을 dist 폴더에 복사했습니다.
) else (
    echo.
    echo === 빌드 실패 ===
)

pause
