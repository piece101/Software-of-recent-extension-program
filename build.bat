@echo off
chcp 65001 >nul
cd /d "%~dp0"
title ReclipSubs 빌드

REM ── 로컬에서 Setup.exe 를 직접 만들 때 사용 ────────────────────────
REM 필요: Python 3.10~3.12,  Inno Setup 6  (winget install -e --id JRSoftware.InnoSetup)

where py >nul 2>nul && (set "PY=py") || (set "PY=python")

echo [1/3] 패키지 설치...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 ( echo 설치 실패 & pause & exit /b 1 )

echo [2/3] PyInstaller 빌드...
%PY% -m PyInstaller packaging\app.spec --noconfirm --clean
if errorlevel 1 ( echo 빌드 실패 & pause & exit /b 1 )

echo [3/3] Inno Setup 설치본 생성...
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 이 없습니다.  winget install -e --id JRSoftware.InnoSetup
  pause & exit /b 1
)
"%ISCC%" /DAppVersion=0.1.0 packaging\installer.iss
if errorlevel 1 ( echo 설치본 생성 실패 & pause & exit /b 1 )

echo.
echo 완료:  packaging\installer_out\ReclipSubs-Setup-0.1.0.exe
pause
