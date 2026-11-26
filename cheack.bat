@echo off
setlocal
rem Change directory to the script's location. This makes the script portable.
cd /d "%~dp0"

echo "Attempting to activate virtual environment..."
rem Activate virtual environment if it exists within the project structure.
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo "Virtual environment activated."
) else (
    echo "WARNING: Virtual environment not found at .\.venv\ . Trying to run with system python."
)

echo "Starting the application (web-cheackerV3.py)..."
rem Run the main python script.
python src\web-cheackerV3.py

rem Pause the console to see any output/errors before it closes.
pause
endlocal
