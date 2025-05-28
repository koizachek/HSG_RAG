@echo off
REM Setup script for the Executive Education RAG Chatbot on Windows

echo Creating virtual environment...
python -m venv venv

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

REM Create .env file from example if it doesn't exist
if not exist .env (
    echo Creating .env file from example...
    copy .env.example .env
    echo Please edit the .env file and add your OpenAI API key.
) else (
    echo .env file already exists.
)

REM Create data directory if it doesn't exist
if not exist data (
    echo Creating data directory...
    mkdir data
)

echo.
echo Setup completed!
echo.
echo To activate the virtual environment, run:
echo   venv\Scripts\activate.bat
echo.
echo To run the chatbot, run:
echo   python main.py
echo.
echo To run the complete pipeline (scraping, processing, vector database setup, and chatbot), run:
echo   python main.py --pipeline
echo.
echo For more options, run:
echo   python main.py --help
echo.

pause
