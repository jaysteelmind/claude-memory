#!/bin/bash
# =============================================================================
# DMM Global Update Script
# =============================================================================
# Usage: dmm-update
#    or: ~/.dmm-system/scripts/update.sh
#    or: curl -sSL https://raw.githubusercontent.com/anthropic/claude-memory/main/scripts/update.sh | bash
#
# Updates DMM global installation at ~/.dmm-system
# =============================================================================
set -euo pipefail

DMM_HOME="${DMM_HOME:-$HOME/.dmm-system}"
DMM_REPO="${DMM_REPO:-https://github.com/anthropic/claude-memory.git}"
DMM_BRANCH="${DMM_BRANCH:-main}"

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

# Error handler
error_exit() {
    log_error "$1"
    exit 1
}

# Print banner
print_banner() {
    echo -e "${CYAN}"
    echo "=============================================="
    echo "  DMM - Dynamic Markdown Memory"
    echo "  Update Script"
    echo "=============================================="
    echo -e "${NC}"
}

# Check if DMM is installed
check_installation() {
    log_step "Checking existing installation..."
    
    if [ ! -d "$DMM_HOME" ]; then
        error_exit "DMM is not installed at ${DMM_HOME}. Run install.sh first."
    fi
    
    if [ ! -f "$DMM_HOME/pyproject.toml" ]; then
        error_exit "Invalid DMM installation at ${DMM_HOME}. Missing pyproject.toml."
    fi
    
    # Get current version
    local current_version
    current_version=$(cd "$DMM_HOME" && poetry version -s 2>/dev/null || echo "unknown")
    log_info "Current version: ${current_version}"
}

# Stop running daemon
stop_daemon() {
    log_step "Stopping DMM daemon if running..."
    
    if [ -x "$DMM_HOME/bin/dmm" ]; then
        "$DMM_HOME/bin/dmm" daemon stop 2>/dev/null || true
    fi
    
    # Clean up PID file
    local pid_file="/tmp/dmm.pid"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null || echo "")
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
        fi
        rm -f "$pid_file"
    fi
    
    log_info "Daemon stopped"
}

# Backup current installation
backup_current() {
    log_step "Creating backup..."
    
    local backup_dir="${DMM_HOME}.update-backup.$(date +%Y%m%d%H%M%S)"
    
    # Only backup essential config files, not entire installation
    mkdir -p "$backup_dir"
    
    # Backup config if exists
    if [ -d "$DMM_HOME/config" ]; then
        cp -r "$DMM_HOME/config" "$backup_dir/"
    fi
    
    # Backup poetry.lock for reproducibility
    if [ -f "$DMM_HOME/poetry.lock" ]; then
        cp "$DMM_HOME/poetry.lock" "$backup_dir/"
    fi
    
    log_info "Backup created at ${backup_dir}"
    echo "$backup_dir"
}

# Update from git or local
update_source() {
    log_step "Updating source code..."
    
    cd "$DMM_HOME" || error_exit "Failed to change to DMM_HOME"
    
    # Check if this is a git repository
    if [ -d ".git" ]; then
        log_info "Updating from git repository..."
        
        # Stash any local changes
        git stash 2>/dev/null || true
        
        # Fetch and reset to latest
        git fetch origin "$DMM_BRANCH" || error_exit "Failed to fetch updates"
        git reset --hard "origin/$DMM_BRANCH" || error_exit "Failed to reset to latest"
        
        log_info "Source updated from git"
    else
        # Not a git repo - check if we can find a local source
        local script_dir
        script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        local source_repo
        source_repo="$(dirname "$script_dir")"
        
        if [ "$source_repo" != "$DMM_HOME" ] && [ -f "${source_repo}/pyproject.toml" ]; then
            log_info "Updating from local source: ${source_repo}"
            
            # Sync files (exclude runtime data)
            rsync -a --delete \
                  --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
                  --exclude='*.pyc' --exclude='.pytest_cache' --exclude='dist' \
                  --exclude='.dmm' --exclude='*.egg-info' --exclude='config' \
                  "${source_repo}/" "$DMM_HOME/" || error_exit "Failed to sync files"
            
            log_info "Source updated from local"
        else
            log_warn "Cannot determine update source. Skipping source update."
            log_warn "To update, reinstall: ./scripts/install.sh"
        fi
    fi
}

# Update dependencies
update_dependencies() {
    log_step "Updating dependencies..."
    
    cd "$DMM_HOME" || error_exit "Failed to change to DMM_HOME"
    
    # Update lock file and install
    poetry lock --no-update 2>/dev/null || true
    poetry install --no-interaction || error_exit "Failed to install dependencies"
    
    log_info "Dependencies updated"
}

# Verify update
verify_update() {
    log_step "Verifying update..."
    
    export PATH="$DMM_HOME/bin:$PATH"
    
    if "$DMM_HOME/bin/dmm" --version >/dev/null 2>&1; then
        local new_version
        new_version=$("$DMM_HOME/bin/dmm" --version 2>/dev/null || echo "unknown")
        log_info "DMM updated successfully: ${new_version}"
    else
        cd "$DMM_HOME"
        if poetry run dmm --version >/dev/null 2>&1; then
            log_info "DMM updated successfully (via poetry)"
        else
            error_exit "Update verification failed"
        fi
    fi
}

# Print completion message
print_completion() {
    local new_version
    new_version=$(cd "$DMM_HOME" && poetry version -s 2>/dev/null || echo "unknown")
    
    echo ""
    echo -e "${GREEN}=============================================="
    echo "  DMM Update Complete"
    echo "==============================================${NC}"
    echo ""
    echo "Version: ${new_version}"
    echo "Location: ${DMM_HOME}"
    echo ""
    echo -e "${CYAN}To restart the daemon:${NC}"
    echo "  dmm daemon start"
    echo ""
}

# Main update flow
main() {
    print_banner
    check_installation
    stop_daemon
    backup_current
    update_source
    update_dependencies
    verify_update
    print_completion
}

# Run main
main "$@"
