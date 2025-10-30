#!/bin/bash

# Script to run the FastAPI backend

echo "🚀 Starting Futbolito Backend..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
    echo ""
    echo "Installing dependencies..."
    source venv/bin/activate
    pip install -r requirements.txt
    echo "✓ Dependencies installed"
else
    source venv/bin/activate
fi

# Check if .env exists
if [ ! -f "../.env" ]; then
    echo "⚠️  .env file not found!"
    echo "Please copy .env.example to .env and add your API keys"
    exit 1
fi

echo ""
echo "✓ Backend starting on http://localhost:8000"
echo "✓ API docs available at http://localhost:8000/docs"
echo "✓ Press Ctrl+C to stop"
echo ""

cd src
uvicorn app:app --host 127.0.0.1 --port 8000 --reload

