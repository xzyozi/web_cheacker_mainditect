import os

# This script generates a .bat file to easily run the main application.

# Content of the .bat file to be created.
# It activates the virtual environment and runs the main Python script.
BAT_CONTENT = """@echo off
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
python web-cheackerV3.py

rem Pause the console to see any output/errors before it closes.
pause
endlocal
"""

FILE_NAME = "cheack.bat"

def create_shortcut():
    """Writes the BAT_CONTENT to the specified FILE_NAME."""
    try:
        # Create the .bat file in the project's root directory.
        with open(FILE_NAME, "w", encoding="utf-8") as f:
            f.write(BAT_CONTENT)
        print(f"Successfully created shortcut: '{os.path.abspath(FILE_NAME)}'")
        print(f"You can now run '{FILE_NAME}' to start the application.")
    except IOError as e:
        print(f"Error: Unable to create file '{FILE_NAME}': {e}")

if __name__ == "__main__":
    print("--- Shortcut Creator ---")
    create_shortcut()
    print("------------------------")