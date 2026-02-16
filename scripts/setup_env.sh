#!/bin/bash
set -e

echo "Setting up BDI Verification Environment..."

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "RELEASE WARNING: Docker is not installed or not in PATH."
    echo "Sandbox execution (Phase 4) will fallback to subprocess or fail."
else
    echo "Docker found."
fi

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Setup complete."
