#!/bin/bash
# Quick Start Script for Ralph with API Credentials

set -e  # Exit on error

echo "════════════════════════════════════════════════"
echo "  Ralph BDI-LLM Framework - Quick Start"
echo "════════════════════════════════════════════════"
echo

# Load environment variables
echo "📦 Loading API credentials..."
source .ralph_env.sh
echo

# Reset session to clear stale state
echo "🔄 Resetting Ralph session..."
ralph --reset-session
echo

# Start monitoring
echo "🚀 Starting Ralph monitor..."
echo "   Press Ctrl+C to stop"
echo
ralph --monitor
