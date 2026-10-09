@echo off
REM CW Protocol Sender - Windows Installation Script
REM Installs Python dependencies and creates launcher batch files

echo ======================================
echo CW Protocol Sender - Windows Installer
echo ======================================
echo.

REM Check Python installation
echo Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    echo.
    echo Please install Python 3.6 or later from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] Found Python %PYTHON_VERSION%
echo.

REM Get installation directory
set INSTALL_DIR=%~dp0
echo Installation directory: %INSTALL_DIR%
echo.

REM Install Python dependencies
echo Installing Python dependencies...
echo ------------------------------------
echo.

REM Install pyserial (required)
echo Installing pyserial (USB serial support)...
python -m pip install --user pyserial>=3.5
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install pyserial
    pause
    exit /b 1
)
echo [OK] pyserial installed
echo.

REM Install audio dependencies (optional)
echo Installing audio dependencies (optional)...
python -m pip install --user pyaudio>=0.2.11 numpy>=1.19.0
if %errorlevel% neq 0 (
    echo [WARNING] Audio dependencies failed (optional)
    echo   Audio sidetone will not work without PyAudio
    echo.
    echo   To enable audio, install Visual C++ Redistributable:
    echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo.
    echo   Then run: python -m pip install pyaudio numpy
    echo.
    echo   Continuing without audio (senders will work, just no sidetone)...
    timeout /t 3 >nul
) else (
    echo [OK] Audio support installed (PyAudio + NumPy)
)
echo.

REM Install websockets (optional)
echo Installing WebSocket support (optional)...
python -m pip install --user websockets>=10.0
if %errorlevel% neq 0 (
    echo [WARNING] WebSocket installation failed (optional)
    echo   Only needed for web platform sender (cw_usb_key_sender_web.py)
) else (
    echo [OK] WebSocket support installed
)
echo.

REM Create launcher batch files
echo Creating launcher commands...
echo ------------------------------------
echo.

REM Create cw-usb-sender.bat
echo @echo off > "%USERPROFILE%\cw-usb-sender.bat"
echo REM CW USB Key Sender (TCP with Timestamps - WiFi optimized) >> "%USERPROFILE%\cw-usb-sender.bat"
echo cd /d "%INSTALL_DIR%" >> "%USERPROFILE%\cw-usb-sender.bat"
echo python cw_usb_key_sender_tcp_ts.py %%* >> "%USERPROFILE%\cw-usb-sender.bat"

REM Create cw-auto-sender.bat
echo @echo off > "%USERPROFILE%\cw-auto-sender.bat"
echo REM CW Auto Sender (Text-to-CW, TCP with Timestamps) >> "%USERPROFILE%\cw-auto-sender.bat"
echo cd /d "%INSTALL_DIR%" >> "%USERPROFILE%\cw-auto-sender.bat"
echo python cw_auto_sender_tcp_ts.py %%* >> "%USERPROFILE%\cw-auto-sender.bat"

REM Create cw-web-sender.bat
echo @echo off > "%USERPROFILE%\cw-web-sender.bat"
echo REM CW Web Platform Sender (WebSocket to Cloudflare Worker) >> "%USERPROFILE%\cw-web-sender.bat"
echo cd /d "%INSTALL_DIR%..\web_platform_tcp" >> "%USERPROFILE%\cw-web-sender.bat"
echo python cw_usb_key_sender_web.py %%* >> "%USERPROFILE%\cw-web-sender.bat"

REM Create cw-auto-web-sender.bat
echo @echo off > "%USERPROFILE%\cw-auto-web-sender.bat"
echo REM CW Automated Web Sender (Text-to-CW via WebSocket) >> "%USERPROFILE%\cw-auto-web-sender.bat"
echo cd /d "%INSTALL_DIR%..\web_platform_tcp" >> "%USERPROFILE%\cw-auto-web-sender.bat"
echo python cw_auto_sender_web.py %%* >> "%USERPROFILE%\cw-auto-web-sender.bat"

echo [OK] Created launchers in %USERPROFILE%
echo.

REM Copy example config to home directory
if not exist "%USERPROFILE%\.cw_sender.ini" (
    echo Creating example config file...
    copy "%INSTALL_DIR%cw_sender.ini.example" "%USERPROFILE%\.cw_sender.ini" >nul
    echo [OK] Created %USERPROFILE%\.cw_sender.ini
    echo   Edit this file to set your default host, WPM, callsign, etc.
) else (
    echo [WARNING] %USERPROFILE%\.cw_sender.ini already exists (not overwriting)
)
echo.

REM Installation complete
echo ======================================
echo [SUCCESS] Installation Complete!
echo ======================================
echo.
echo Available commands:
echo   %USERPROFILE%\cw-usb-sender.bat       - USB key sender (physical paddle/key)
echo   %USERPROFILE%\cw-auto-sender.bat      - Automated text-to-CW sender (TCP)
echo   %USERPROFILE%\cw-web-sender.bat       - Web platform sender (physical key via WebSocket)
echo   %USERPROFILE%\cw-auto-web-sender.bat  - Automated text-to-CW sender (WebSocket)
echo.
echo Quick Start:
echo   1. Edit config: notepad %USERPROFILE%\.cw_sender.ini
echo      (Set your receiver IP, WPM, callsign)
echo.
echo   2. Run with config:
echo      %USERPROFILE%\cw-usb-sender.bat
echo.
echo   3. Or override with CLI args:
echo      %USERPROFILE%\cw-usb-sender.bat 192.168.1.100 --wpm 25 --mode iambic-b
echo.
echo Help:
echo   %USERPROFILE%\cw-usb-sender.bat --help
echo.
echo Documentation:
echo   %INSTALL_DIR%README.md
echo   %INSTALL_DIR%DOC\CW_PROTOCOL_SPECIFICATION.md
echo.
echo.
echo OPTIONAL: Add to PATH for easier access
echo   1. Press Windows key, search "environment variables"
echo   2. Click "Environment Variables" button
echo   3. Under "User variables", select "Path", click "Edit"
echo   4. Click "New", add: %USERPROFILE%
echo   5. Click OK, restart Command Prompt
echo.
echo   Then you can just run: cw-usb-sender.bat
echo.
pause
