@echo off
setlocal EnableExtensions

if /i "%~1"=="--server" goto server
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Project virtual environment .venv is missing.
    echo Run: python -m venv .venv
    echo Then run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    goto failed
)
if not exist ".env" (
    echo .env is missing. Configure database settings using .env.example.
    goto failed
)

powershell.exe -NoProfile -Command "$s=Get-Service -Name MySQL97 -ErrorAction SilentlyContinue; if ($s -and $s.Status -eq 'Running') { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo MySQL97 is stopped. Attempting to start it...
    net start MySQL97
    if errorlevel 1 (
        echo Cannot start MySQL97. In an administrator PowerShell, run: Start-Service MySQL97
        goto failed
    )
)

set "PORT=8004"
if not "%~1"=="" set "PORT=%~1"
echo(%PORT%| findstr /R "^[1-9][0-9]*$" >nul
if errorlevel 1 (
    echo Port must be a positive integer.
    goto failed
)

:select_port
powershell.exe -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Headers @{'X-Local-Settings'='1'} 'http://127.0.0.1:%PORT%/api/v1/model-settings'; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if not errorlevel 1 goto open_browser
powershell.exe -NoProfile -Command "try { $c=New-Object System.Net.Sockets.TcpClient; $c.Connect('127.0.0.1',%PORT%); $c.Close(); exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto launch_server
echo Port %PORT% is occupied by another or older service. Trying next port.
set /a PORT+=1
if %PORT% GTR 8010 (
    echo Ports 8004 through 8010 are occupied. Close an unused service and retry.
    goto failed
)
goto select_port

:launch_server
echo Starting GaoKaoAgent on port %PORT%...
start "GaoKaoAgent Server" "%ComSpec%" /c ""%~f0" --server %PORT%"
for /l %%I in (1,1,25) do (
    powershell.exe -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:%PORT%/api/health'; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
    if not errorlevel 1 goto open_browser
    ping -n 2 127.0.0.1 >nul
)
echo Server did not start within 25 seconds. Check the new server window for errors.
goto failed

:open_browser
powershell.exe -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:%PORT%/api/health/db'; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; exit 1" >nul 2>&1
if errorlevel 1 (
    echo Server started, but database connection failed. Check .env and MySQL97.
    goto failed
)
echo Project URL: http://127.0.0.1:%PORT%/
echo Model settings are available in the left navigation.
start "" "http://127.0.0.1:%PORT%/"
exit /b 0

:server
cd /d "%~dp0backend"
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port %~2
if errorlevel 1 (
    echo Server stopped with an error. Review the message above.
    pause
)
exit /b

:failed
echo.
pause
exit /b 1
