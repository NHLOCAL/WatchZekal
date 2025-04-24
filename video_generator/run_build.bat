@echo off
setlocal enabledelayedexpansion

:: Ask the user which script to run
echo Choose which script to run:
echo 1 - build-v2-multi-languages.py
echo 2 - build-shorts-multi-languages.py
set /p script_choice=Enter your choice (1 or 2):  

if "%script_choice%"=="1" (
    set script_name=build-v2-multi-languages.py
) else if "%script_choice%"=="2" (
    set script_name=build-shorts-multi-languages.py
) else (
    echo Invalid choice. Exiting...
    exit /b
)

:: Get range and language input
set /p start_num=Enter start number:  
set /p end_num=Enter end number:  
set /p lang_code=Enter language code:  

echo Running %script_name% for range %start_num% to %end_num% with language %lang_code%...
for /L %%i in (%start_num%,1,%end_num%) do (
    echo Executing: %script_name% %%i %lang_code%
    %script_name% %%i %lang_code%
)

echo Process completed!
pause
