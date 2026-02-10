@echo off
set LOCALHOST=%COMPUTERNAME%
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 66088)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 48696)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 73204)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 51504)

del /F cleanup-ansys-it-calcfarm12-51504.bat
