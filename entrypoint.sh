#!/bin/bash
set -e

# Clean up stale PID file from previous container run
SCHEDULER_PID_FILE="data/skills/scheduler/scheduler.pid"
if [ -f "$SCHEDULER_PID_FILE" ]; then
    echo "[entrypoint] Removing stale scheduler PID file"
    rm -f "$SCHEDULER_PID_FILE"
fi

# Start scheduler daemon in background
python data/skills/scheduler/main.py &
SCHEDULER_PID=$!
echo "[entrypoint] Scheduler started (PID=$SCHEDULER_PID)"

# Start the bot (foreground — container exits when bot exits)
exec python run_qq.py
