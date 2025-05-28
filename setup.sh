#!/bin/bash
# Setup script for the Executive Education RAG Chatbot

# Create a virtual environment
echo "Creating virtual environment..."
python -m venv venv

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env file from example if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env file from example..."
    cp .env.example .env
    echo "Please edit the .env file and add your OpenAI API key."
else
    echo ".env file already exists."
fi

# Create data directory if it doesn't exist
if [ ! -d data ]; then
    echo "Creating data directory..."
    mkdir -p data
fi

echo ""
echo "Setup completed!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the chatbot, run:"
echo "  python main.py"
echo ""
echo "To run the complete pipeline (scraping, processing, vector database setup, and chatbot), run:"
echo "  python main.py --pipeline"
echo ""
echo "For more options, run:"
echo "  python main.py --help"
echo ""
