@echo off
net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo Please run this script with Administrator privileges
    timeout 10 > NUL
    EXIT /B 1
)
SET cdpath=%~dp0
echo Setting the system environment variable DOCKER_HOST
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v DOCKER_HOST /t REG_SZ /d tcp://:2376 /f
echo Setting the system environment variable DOCKER_TLS
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v DOCKER_TLS_VERIFY /t REG_SZ /d 1 /f
echo Configuring the Docker daemon for TLS
if not exist c:\ProgramData\docker\certs.d\ mkdir c:\ProgramData\docker\certs.d\
xcopy /O %cdpath%server\* c:\ProgramData\docker\certs.d\
echo Configuring the Docker client to connect using TLS for the current user
if not exist c:\Users\%username%\.docker\ mkdir c:\Users\%username%\.docker\
xcopy /O %cdpath%client\* c:\Users\%username%\.docker\
echo Restarting Docker
net stop Docker
net start Docker
echo All done. Docker is now configured for TLS.
echo Please complete the preparation on the control domain console.
timeout 10 > NUL
EXIT /b 0
