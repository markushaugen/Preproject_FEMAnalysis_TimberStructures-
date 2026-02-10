@echo off
set LOCALHOST=%COMPUTERNAME%
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 56208)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 48276)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 23136)
if /i "%LOCALHOST%"=="it-calcfarm12" (taskkill /f /pid 9560)

del /F cleanup-ansys-it-calcfarm12-9560.bat
