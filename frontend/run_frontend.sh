#!/bin/bash

# Script to run the React frontend

echo "🚀 Starting Futbolito Frontend..."

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "⚠️  node_modules not found!"
    echo "Installing dependencies..."
    npm install
    echo "✓ Dependencies installed"
fi

echo ""
echo "✓ Frontend starting on http://localhost:5173"
echo "✓ Press Ctrl+C to stop"
echo ""

npm run dev

