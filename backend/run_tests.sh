#!/bin/bash
# VERITAS AI Backend Test Runner
# Run this after installing dependencies

set -e

echo "============================"
echo "VERITAS AI Backend Tests"
echo "============================"
echo

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
    source venv/bin/activate
    echo "Installing dependencies..."
    pip install -r requirements.txt
    pip install pytest pytest-asyncio
else
    source venv/bin/activate
fi

echo
echo "Running tests..."
python -m pytest tests/ -v --tb=short

echo
echo "Test run complete."