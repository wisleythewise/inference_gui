#!/bin/bash

# Start the Robot Control Backend

echo "Starting S7 Robot Control Backend..."

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "No virtual environment found. Creating one..."
    python3 -m venv venv
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "Loading environment variables from .env..."
    export $(cat .env | grep -v '^#' | xargs)
fi

# Start the server
echo "Starting FastAPI server..."
python app_v2.py