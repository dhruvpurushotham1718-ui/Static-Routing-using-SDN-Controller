#!/bin/bash
# =============================================================
# SDN Static Routing — Quick Launcher
# =============================================================
# Usage:
#   chmod +x run.sh
#   ./run.sh          # start controller + topology
#   ./run.sh test     # start controller + run regression tests
# =============================================================

POX_DIR="$HOME/pox"
CTRL_LOG="/tmp/pox_controller.log"

if [ ! -d "$POX_DIR" ]; then
    echo "[ERROR] POX not found at $POX_DIR"
    echo "        Clone it with: git clone https://github.com/noxrepo/pox.git ~/pox"
    exit 1
fi

# Copy controller to POX ext folder
cp static_routing.py "$POX_DIR/ext/"

# Kill any existing POX instance
pkill -f "pox.py" 2>/dev/null
sleep 1

echo "[*] Starting POX controller in background..."
cd "$POX_DIR"
./pox.py log.level --DEBUG static_routing > "$CTRL_LOG" 2>&1 &
POX_PID=$!
echo "[*] POX PID: $POX_PID  (logs: $CTRL_LOG)"

# Give controller time to bind port 6633
sleep 2

cd - > /dev/null

if [ "$1" == "test" ]; then
    echo "[*] Running regression tests..."
    sudo python3 regression_test.py
else
    echo "[*] Starting Mininet topology..."
    sudo python3 topology.py
fi

# Cleanup
echo "[*] Stopping POX controller..."
kill $POX_PID 2>/dev/null
