#!/bin/bash
# Auto-trader wrapper script with sleep prevention and auto-restart.
#
# Features:
# - Uses caffeinate to prevent macOS sleep during market hours
# - Auto-restarts the trader if it crashes
# - Max 5 restarts per day to prevent infinite loops
# - Logs restart events
#
# Usage:
#   ./scripts/run_auto_trader.sh
#   ./scripts/run_auto_trader.sh --strategies factor_composite simple_momentum

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

LOG_FILE="logs/auto_trader.log"
RESTART_LOG="logs/auto_trader_restarts.log"
PID_FILE="logs/auto_trader.pid"
MAX_RESTARTS_PER_DAY=5
RESTART_COUNT=0
LAST_RESTART_DATE=""

# Default strategies
STRATEGIES="${@:---strategies factor_composite simple_momentum}"

# Activate virtual environment
source venv/bin/activate

# Ensure logs directory exists
mkdir -p logs

log_restart() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$RESTART_LOG"
    echo "$1"
}

cleanup() {
    log_restart "Wrapper script stopped (signal received)"
    # Kill caffeinate if running
    if [ -n "$CAFFEINATE_PID" ]; then
        kill "$CAFFEINATE_PID" 2>/dev/null || true
    fi
    # Kill trader if running
    if [ -n "$TRADER_PID" ] && kill -0 "$TRADER_PID" 2>/dev/null; then
        kill "$TRADER_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    exit 0
}

trap cleanup SIGINT SIGTERM

log_restart "=== Auto-trader wrapper starting ==="
log_restart "Strategies: $STRATEGIES"

while true; do
    TODAY=$(date '+%Y-%m-%d')

    # Reset restart counter each day
    if [ "$TODAY" != "$LAST_RESTART_DATE" ]; then
        RESTART_COUNT=0
        LAST_RESTART_DATE="$TODAY"
    fi

    # Check restart limit
    if [ "$RESTART_COUNT" -ge "$MAX_RESTARTS_PER_DAY" ]; then
        log_restart "ERROR: Max restarts ($MAX_RESTARTS_PER_DAY) reached today. Waiting until tomorrow."
        sleep 3600  # Wait 1 hour and check again
        continue
    fi

    # Start caffeinate to prevent sleep (only prevents idle sleep, not lid close)
    # -i: prevent idle sleep
    # -s: prevent system sleep (when on AC power)
    caffeinate -is &
    CAFFEINATE_PID=$!
    log_restart "caffeinate started (PID: $CAFFEINATE_PID) - preventing system sleep"

    # Start the auto-trader
    log_restart "Starting auto-trader (attempt $((RESTART_COUNT + 1))/$MAX_RESTARTS_PER_DAY today)"
    # auto_trader.py writes to logs/auto_trader.log via its own FileHandler
    # Don't redirect stdout/stderr to same file (causes duplicate lines)
    python -m scripts.auto_trader $STRATEGIES > /dev/null 2>&1 &
    TRADER_PID=$!
    echo "$TRADER_PID" > "$PID_FILE"
    log_restart "Auto-trader started (PID: $TRADER_PID)"

    # Wait for it to exit
    wait "$TRADER_PID" 2>/dev/null
    EXIT_CODE=$?

    # Stop caffeinate
    kill "$CAFFEINATE_PID" 2>/dev/null || true

    # Check if it was a clean shutdown (Ctrl+C or SIGTERM)
    if [ "$EXIT_CODE" -eq 0 ] || [ "$EXIT_CODE" -eq 130 ] || [ "$EXIT_CODE" -eq 143 ]; then
        log_restart "Auto-trader stopped cleanly (exit code: $EXIT_CODE)"
        rm -f "$PID_FILE"
        exit 0
    fi

    # Crashed - increment counter and restart
    RESTART_COUNT=$((RESTART_COUNT + 1))
    log_restart "Auto-trader crashed (exit code: $EXIT_CODE). Restarting in 30s... ($RESTART_COUNT/$MAX_RESTARTS_PER_DAY today)"

    sleep 30
done
