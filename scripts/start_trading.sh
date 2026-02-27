#!/bin/bash
# Start the automated trading system
# This script starts the auto-trader which will:
# 1. Check for signals every 5 minutes
# 2. Execute trades automatically
# 3. Run both Dual Momentum and Swing Momentum strategies

cd "$(dirname "$0")/.."

# Activate virtual environment
source venv/bin/activate

# Create logs directory if needed
mkdir -p logs

echo "=============================================="
echo "  QUANT TRADING BOT - AUTO TRADER"
echo "=============================================="
echo ""
echo "Starting automated trading service..."
echo "Strategies: Dual Momentum (monthly), Swing Momentum (daily)"
echo "Check Interval: Every 5 minutes during market hours"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run the auto-trader
python -m scripts.auto_trader --interval 300

echo ""
echo "Auto-trader stopped."
