#!/bin/bash
# =============================================================================
# DMM Installation Script
# =============================================================================
#
# Usage: ./start.sh
#
# This script:
# 1. Runs the DMM bootstrap (installs Poetry, dependencies, dmm command)
# 2. Installs the claudex command to /usr/local/bin/
# 3. Verifies installation
#
# After running this script, just type 'claudex' from anywhere.
#
# =============================================================================
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  DMM Installation${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$HOME/projects/claude-memory"

# Verify we're in the right location
if [ "${SCRIPT_DIR}" != "${PROJECT_DIR}" ]; then
    echo -e "${RED}Error: This script must be run from ~/projects/claude-memory${NC}"
    echo -e "${RED}Current location: ${SCRIPT_DIR}${NC}"
    echo -e "${YELLOW}Please run:${NC}"
    echo -e "  cd ~/projects/claude-memory"
    echo -e "  ./start.sh"
    exit 1
fi

# Step 1: Run bootstrap
echo -e "${BLUE}[1/3] Running DMM bootstrap...${NC}"
./bin/dmm-bootstrap
echo ""

# Step 2: Install claudex command
echo -e "${BLUE}[2/3] Installing claudex command...${NC}"

cat > /tmp/claudex << 'CLAUDEX'
#!/bin/bash
# =============================================================================
# claudex - Claude Code with DMM from claude-memory project
# =============================================================================
set -e

# Hardwired project directory
PROJECT_DIR="$HOME/projects/claude-memory"
DMM_PORT="${DMM_PORT:-7433}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Track if we started the daemon
DAEMON_STARTED_BY_US=false

# Cleanup function
cleanup() {
    if [ "${DAEMON_STARTED_BY_US}" = true ]; then
        echo -e "\n${YELLOW}Stopping DMM daemon...${NC}"
        dmm daemon stop 2>/dev/null || true
        echo -e "${GREEN}DMM daemon stopped${NC}"
    fi
}

trap cleanup EXIT INT TERM

# Bootstrap DMM if not installed
if ! command -v dmm &> /dev/null; then
    echo -e "${YELLOW}DMM not installed. Running bootstrap...${NC}"
    "${PROJECT_DIR}/bin/dmm-bootstrap"
fi

# Start daemon if not running
if curl -sf "http://127.0.0.1:${DMM_PORT}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}DMM daemon already running${NC}"
else
    echo -e "${YELLOW}Starting DMM daemon...${NC}"
    cd "${PROJECT_DIR}"
    dmm daemon start
    DAEMON_STARTED_BY_US=true
    
    for i in {1..30}; do
        if curl -sf "http://127.0.0.1:${DMM_PORT}/health" > /dev/null 2>&1; then
            echo -e "${GREEN}DMM daemon ready${NC}"
            break
        fi
        [ $i -eq 30 ] && echo -e "${RED}Daemon failed to start${NC}" && exit 1
        sleep 1
    done
fi

# Launch Claude from project directory
cd "${PROJECT_DIR}"
echo -e "${GREEN}Starting Claude Code in ${PROJECT_DIR}${NC}"
exec claude --dangerously-skip-permissions "$@"
CLAUDEX

chmod +x /tmp/claudex
sudo cp /tmp/claudex /usr/local/bin/claudex
sudo chmod +x /usr/local/bin/claudex
rm /tmp/claudex
echo -e "${GREEN}  claudex installed to /usr/local/bin/${NC}"
echo ""

# Step 3: Verify installation
echo -e "${BLUE}[3/3] Verifying installation...${NC}"

if command -v dmm &> /dev/null; then
    echo -e "${GREEN}  dmm command: OK${NC}"
else
    echo -e "${RED}  dmm command: FAILED${NC}"
    exit 1
fi

if command -v claudex &> /dev/null; then
    echo -e "${GREEN}  claudex command: OK${NC}"
else
    echo -e "${RED}  claudex command: FAILED${NC}"
    exit 1
fi

if [ -d "${PROJECT_DIR}/.dmm" ]; then
    echo -e "${GREEN}  .dmm directory: OK${NC}"
else
    echo -e "${RED}  .dmm directory: FAILED${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Installation Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "To start Claude with DMM, run from anywhere:"
echo -e "  ${BLUE}claudex${NC}"
echo ""
