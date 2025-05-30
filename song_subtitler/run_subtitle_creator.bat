@echo off
chcp 65001 > nul
cls
echo ============================================================
echo == YouTube Subtitled Video Creator - Launcher ==
echo ============================================================
echo.

set "PYTHON_EXE=python"
set "SCRIPT_NAME=main.py"
set "CMD_ARGS="

:MODE_CHOICE
echo Choose an operation mode:
echo 1. Add and process a new song
echo 2. Select and process an existing song from the list
echo.
set /p mode_choice="Enter your choice (1 or 2): "

if "%mode_choice%"=="1" goto :ADD_SONG
if "%mode_choice%"=="2" goto :SELECT_SONG

echo Invalid choice. Please enter 1 or 2.
goto :MODE_CHOICE

REM --- ADD NEW SONG SECTION ---
:ADD_SONG
echo.
echo --- Adding a New Song ---
set "CMD_ARGS=--add"

:SONG_NAME_INPUT
set /p song_name="Enter Song Name (Required, e.g., My Awesome Song): "
if "%song_name%"=="" (
    echo Song Name cannot be empty.
    goto :SONG_NAME_INPUT
)
set "CMD_ARGS=%CMD_ARGS% -n "%song_name%""

:SONG_URL_INPUT
set /p youtube_url="Enter YouTube URL (Required): "
if "%youtube_url%"=="" (
    echo YouTube URL cannot be empty.
    goto :SONG_URL_INPUT
)
set "CMD_ARGS=%CMD_ARGS% -u "%youtube_url%""

echo.
set /p artist_name="Enter Artist Name (Optional, press Enter to skip): "
if defined artist_name set "CMD_ARGS=%CMD_ARGS% -ar "%artist_name%""

set /p hebrew_name="Enter Hebrew Song Name (Optional, press Enter to skip): "
if defined hebrew_name set "CMD_ARGS=%CMD_ARGS% -hn "%hebrew_name%""

set /p source_mp3_path="Enter full path to source MP3 file (Optional, press Enter to skip): "
if defined source_mp3_path set "CMD_ARGS=%CMD_ARGS% -sm "%source_mp3_path%""

goto :COMMON_OPTIONS

REM --- SELECT EXISTING SONG SECTION ---
:SELECT_SONG
echo.
echo --- Selecting an Existing Song ---
set "CMD_ARGS="

:SONG_IDENTIFIER_INPUT
set /p song_identifier="Enter Song Identifier (Index, YouTube ID, or Exact Name from list): "
if "%song_identifier%"=="" (
    echo Song Identifier cannot be empty.
    goto :SONG_IDENTIFIER_INPUT
)
set "CMD_ARGS=%CMD_ARGS% -s "%song_identifier%""
goto :COMMON_OPTIONS

REM --- COMMON OPTIONAL PARAMETERS ---
:COMMON_OPTIONS
echo.
echo --- Optional Processing Settings ---

set /p source_lang="Source Language (en/yi) (Optional, press Enter for default from JSON/config): "
if defined source_lang set "CMD_ARGS=%CMD_ARGS% -l "%source_lang%""

set /p lyrics_file_path="Path to Lyrics .txt file (Optional, press Enter to skip): "
if defined lyrics_file_path set "CMD_ARGS=%CMD_ARGS% -lf "%lyrics_file_path%""

set /p source_subs_path="Path to Source Subtitles file (JSON/SRT) (Optional, press Enter to skip): "
if defined source_subs_path set "CMD_ARGS=%CMD_ARGS% -ss "%source_subs_path%""

set /p target_subs_path="Path to Target (Hebrew) Subtitles file (JSON/SRT) (Optional, press Enter to skip): "
if defined target_subs_path set "CMD_ARGS=%CMD_ARGS% -ts "%target_subs_path%""

:FORCE_REGEN_CHOICE
set /p force_regen_choice="Force regenerate subtitles from API (y/n)? (Optional, default n): "
if /i "%force_regen_choice%"=="y" set "CMD_ARGS=%CMD_ARGS% -f"
if /i "%force_regen_choice%"=="n" (
    REM Do nothing, default is not to force
    goto :INTRO_SUB_CHOICE
)
if "%force_regen_choice%"=="" (
    REM Do nothing, default is not to force
    goto :INTRO_SUB_CHOICE
)
echo Invalid choice for force regenerate. Please enter 'y' or 'n'.
goto :FORCE_REGEN_CHOICE


:INTRO_SUB_CHOICE
echo.
echo Available Intro Subtitle Modes:
echo   artist - Show artist name (default)
echo   hebrew - Show Hebrew song name
set /p intro_sub_mode="Intro Subtitle Mode (artist/hebrew) (Optional, press Enter for 'artist'): "
if defined intro_sub_mode (
    if /i "%intro_sub_mode%"=="artist" set "CMD_ARGS=%CMD_ARGS% -is artist"
    if /i "%intro_sub_mode%"=="hebrew" set "CMD_ARGS=%CMD_ARGS% -is hebrew"
    REM If input is something else, main.py will handle it or use its default
) else (
    REM Default is artist, main.py will handle this if -is is not passed or if passed without value
    set "CMD_ARGS=%CMD_ARGS% -is artist"
)


REM --- EXECUTE SCRIPT ---
echo.
echo ============================================================
echo Attempting to run the script with the following arguments:
echo %PYTHON_EXE% %SCRIPT_NAME% %CMD_ARGS%
echo ============================================================
echo.

%PYTHON_EXE% %SCRIPT_NAME% %CMD_ARGS%

echo.
echo ============================================================
echo Script execution finished.
echo ============================================================
pause
exit /b