@echo off
set LOCALHOST=%COMPUTERNAME%
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 15132)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 55988)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 28088)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 39732)

del /F cleanup-ansys-it-calcfarm12-39732.bat
