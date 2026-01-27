#!/bin/bash
# =============================================================================
# DMM Global Uninstallation Script
# =============================================================================
# Usage: ~/.dmm-system/scripts/uninstall.sh
#    or: curl -sSL https://raw.githubusercontent.com/jaysteelmind/claude-memory/main/scripts/uninstall.sh | bash
#
# Removes DMM global installation from ~/.dmm-system
# =============================================================================
set -euo pipefail

DMM_HOME="${DMM_HOME:-$HOME/.dmm-system}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Logging functions
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

# Print banner
print_banner() {
    echo -e "${CYAN}"
    echo "=============================================="
    echo "  DMM - Dynamic Markdown Memory"
    echo "  Uninstallation Script"
    echo "=============================================="
    echo -e "${NC}"
}

# Confirm uninstallation
confirm_uninstall() {
    if [ "${DMM_UNINSTALL_CONFIRM:-}" = "yes" ]; then
        return 0
    fi
    
    echo -e "${YELLOW}This will remove DMM from ${DMM_HOME}${NC}"
    echo ""
    echo "The following will be deleted:"
    echo "  - ${DMM_HOME} (entire directory)"
    echo "  - DMM configuration from shell profiles"
    echo ""
    echo -e "${YELLOW}Project-local .dmm directories will NOT be removed.${NC}"
    echo ""
    read -p "Are you sure you want to uninstall? [y/N] " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Uninstallation cancelled"
        exit 0
    fi
}

# Stop running daemon
stop_daemon() {
    log_step "Stopping DMM daemon if running..."
    
    # Try to stop via dmm command
    if [ -x "$DMM_HOME/bin/dmm" ]; then
        "$DMM_HOME/bin/dmm" daemon stop 2>/dev/null || true
    fi
    
    # Clean up PID file
    local pid_file="/tmp/dmm.pid"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            log_info "Stopping daemon process ${pid}"
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$pid_file"
    fi
    
    log_info "Daemon stopped"
}

# Remove shell configuration
remove_shell_config() {
    log_step "Removing shell configuration..."
    
    local shell_configs=("$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile")
    
    for rc_file in "${shell_configs[@]}"; do
        if [ -f "$rc_file" ]; then
            if grep -q "DMM_HOME" "$rc_file" 2>/dev/null; then
                # Create backup
                cp "$rc_file" "${rc_file}.dmm-backup"
                
                # Remove DMM configuration block (handles multi-line)
                sed -i '/# DMM (Dynamic Markdown Memory)/,/export PATH="\$DMM_HOME\/bin:\$PATH"/d' "$rc_file" 2>/dev/null || \
                sed -i '' '/# DMM (Dynamic Markdown Memory)/,/export PATH="\$DMM_HOME\/bin:\$PATH"/d' "$rc_file" 2>/dev/null || true
                
                # Also remove any standalone DMM_HOME exports
                sed -i '/export DMM_HOME=/d' "$rc_file" 2>/dev/null || \
                sed -i '' '/export DMM_HOME=/d' "$rc_file" 2>/dev/null || true
                
                log_info "Removed DMM configuration from ${rc_file}"
            fi
        fi
    done
}

# Remove installation directory
remove_installation() {
    log_step "Removing DMM installation..."
    
    if [ -d "$DMM_HOME" ]; then
        rm -rf "$DMM_HOME"
        log_info "Removed ${DMM_HOME}"
    else
        log_warn "Installation directory not found: ${DMM_HOME}"
    fi
}

# Remove any global pip installation
remove_pip_package() {
    log_step "Checking for pip-installed DMM package..."
    
    if pip show dmm >/dev/null 2>&1; then
        log_info "Removing pip-installed dmm package"
        pip uninstall dmm -y 2>/dev/null || \
        pip uninstall dmm -y --break-system-packages 2>/dev/null || true
    fi
}

# Clean up temporary files
cleanup_temp() {
    log_step "Cleaning up temporary files..."
    
    # Remove PID files
    rm -f /tmp/dmm.pid 2>/dev/null || true
    rm -f /tmp/dmm.sock 2>/dev/null || true
    rm -f /tmp/dmm-*.log 2>/dev/null || true
    
    log_info "Temporary files cleaned"
}

# Print completion message
print_completion() {
    echo ""
    echo -e "${GREEN}=============================================="
    echo "  DMM Uninstallation Complete"
    echo "==============================================${NC}"
    echo ""
    echo "DMM has been removed from your system."
    echo ""
    echo -e "${YELLOW}Note:${NC}"
    echo "  - Project-local .dmm directories were NOT removed"
    echo "  - To remove project memories: rm -rf /path/to/project/.dmm"
    echo ""
    echo "To reinstall DMM:"
    echo "  curl -sSL https://raw.githubusercontent.com/jaysteelmind/claude-memory/main/scripts/install.sh | bash"
    echo ""
}

# Main uninstallation flow
main() {
    print_banner
    
    # Check if DMM is installed
    if [ ! -d "$DMM_HOME" ]; then
        log_warn "DMM is not installed at ${DMM_HOME}"
        log_info "Nothing to uninstall"
        exit 0
    fi
    
    confirm_uninstall
    stop_daemon
    remove_shell_config
    remove_pip_package
    remove_installation
    cleanup_temp
    print_completion
}

# Run main
main "$@"
