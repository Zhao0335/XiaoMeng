#!/bin/bash
set -e

# Clean up stale PID file from previous container run
# (scheduler daemon is started and managed by run_qq.py, not here)
SCHEDULER_PID_FILE="data/skills/scheduler/scheduler.pid"
if [ -f "$SCHEDULER_PID_FILE" ]; then
    echo "[entrypoint] Removing stale scheduler PID file"
    rm -f "$SCHEDULER_PID_FILE"
fi

# Start the bot (foreground — container exits when bot exits)
# run_qq.py starts the scheduler daemon internally with auto-restart
exec python run_qq.py
