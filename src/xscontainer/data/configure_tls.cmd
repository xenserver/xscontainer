@echo off
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo Please run this script with Administrator privileges.
    timeout 30
    EXIT /B 1
)
SET cdpath=%~dp0
if not exist %PROGRAMDATA%\docker\ (
    echo Error: Could not find Docker in %PROGRAMDATA%\docker\.
    echo Please install Docker before running this script.
    timeout 30
    EXIT /B 1
)
echo Setting the system environment variable DOCKER_HOST.
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v DOCKER_HOST /t REG_SZ /d tcp://:2376 /f || goto :ERRORHANDLER
echo Setting the system environment variable DOCKER_TLS.
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v DOCKER_TLS_VERIFY /t REG_SZ /d 1 /f || goto :ERRORHANDLER
echo Configuring the Docker daemon for TLS using %PROGRAMDATA%\Docker\certs.d
if not exist %PROGRAMDATA%\docker\certs.d\ (
    mkdir %PROGRAMDATA%\docker\certs.d\ || goto :ERRORHANDLER
)
icacls.exe %PROGRAMDATA%\docker\certs.d\ /T /grant BUILTIN\Administrators:(OI)(CI)F /grant BUILTIN\Administrators:F /grant SYSTEM:(OI)(CI)F /grant SYSTEM:F /inheritance:r || goto :ERRORHANDLER
xcopy /O %cdpath%server\* %PROGRAMDATA%\docker\certs.d\ || goto :ERRORHANDLER
echo Configuring the Docker client in %USERPROFILE%\.docker\ to connect using TLS for the current user.
if not exist %USERPROFILE%\.docker\ (
    mkdir %USERPROFILE%\.docker\ || goto :ERRORHANDLER
)

if not exist %PROGRAMDATA%\docker\config (
    mkdir %PROGRAMDATA%\docker\config || goto :ERRORHANDLER
)
echo Setting up the TLS configuration.
xcopy %cdpath%daemon.json %PROGRAMDATA%\docker\config\ || goto :ERRORHANDLER

icacls.exe %USERPROFILE%\.docker\ /T /grant %USERDOMAIN%\%USERNAME%:(OI)(CI)F /grant %USERDOMAIN%\%USERNAME%:F /inheritance:r || goto :ERRORHANDLER
xcopy /O %cdpath%client\* %USERPROFILE%\.docker\ || goto :ERRORHANDLER
echo Restarting Docker.
net stop Docker || goto :ERRORHANDLER
net start Docker || goto :ERRORHANDLER
echo All done. Docker is now configured for TLS.

echo Checking firewall status.
for /f "tokens=2*" %%a in ('REG QUERY HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\SharedAccess\Parameters\FirewallPolicy\StandardProfile /v EnableFirewall') do set "AppPath=%%~b"
if %AppPath%==0x1 (
    echo Your firewall is currently enabled, please ensure your firewall allows Docker TLS communication as per the documentation.
)
echo Please press enter and complete the preparation on the control domain console.
timeout 10 > NUL
EXIT /b 0
goto :EOF


:ERRORHANDLER
echo Error: Command failed with errorlevel #%errorlevel%.
timeout 30
exit /B %errorlevel%
