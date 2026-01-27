#!/bin/bash
# =============================================================================
# DMM Global Installation Script
# =============================================================================
# Usage: curl -sSL https://raw.githubusercontent.com/jaysteelmind/claude-memory/main/scripts/install.sh | bash
#    or: ./scripts/install.sh
#
# Installs DMM globally to ~/.dmm-system
# =============================================================================
set -euo pipefail

DMM_HOME="${DMM_HOME:-$HOME/.dmm-system}"
DMM_REPO="${DMM_REPO:-https://github.com/jaysteelmind/claude-memory.git}"
DMM_BRANCH="${DMM_BRANCH:-main}"
DMM_VERSION="1.0.0"

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
    echo "  Global Installation Script v${DMM_VERSION}"
    echo "=============================================="
    echo -e "${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Get Python version as comparable integer (311 for 3.11)
get_python_version_int() {
    local python_cmd="$1"
    $python_cmd -c 'import sys; print(sys.version_info.major * 100 + sys.version_info.minor)' 2>/dev/null || echo "0"
}

# Find suitable Python (3.11+)
find_python() {
    local candidates=("python3.13" "python3.12" "python3.11" "python3" "python")
    local min_version=311
    
    for cmd in "${candidates[@]}"; do
        if command_exists "$cmd"; then
            local version_int
            version_int=$(get_python_version_int "$cmd")
            if [ "$version_int" -ge "$min_version" ]; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

# Check prerequisites
check_prerequisites() {
    log_step "Checking prerequisites..."
    
    # Find Python 3.11+
    PYTHON_CMD=$(find_python) || error_exit "Python 3.11+ is required but not found. Please install Python 3.11 or later."
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
    log_info "Python ${PYTHON_VERSION} found (${PYTHON_CMD})"
    
    # Check Git
    if ! command_exists git; then
        error_exit "Git is required but not installed. Please install Git."
    fi
    GIT_VERSION=$(git --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    log_info "Git ${GIT_VERSION} found"
    
    # Check/Install Poetry
    if ! command_exists poetry; then
        log_warn "Poetry not found. Installing..."
        curl -sSL https://install.python-poetry.org | $PYTHON_CMD - || error_exit "Failed to install Poetry"
        export PATH="$HOME/.local/bin:$PATH"
        if ! command_exists poetry; then
            error_exit "Poetry installation failed. Please install manually: https://python-poetry.org/docs/#installation"
        fi
    fi
    POETRY_VERSION=$(poetry --version | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
    log_info "Poetry ${POETRY_VERSION} found"
}

# Backup existing installation
backup_existing() {
    if [ -d "$DMM_HOME" ]; then
        local backup_dir="${DMM_HOME}.backup.$(date +%Y%m%d%H%M%S)"
        log_warn "Existing installation found at ${DMM_HOME}"
        log_info "Creating backup at ${backup_dir}"
        mv "$DMM_HOME" "$backup_dir" || error_exit "Failed to backup existing installation"
    fi
}

# Clone or copy repository
install_repository() {
    log_step "Installing DMM to ${DMM_HOME}..."
    
    # Check if we're running from within the repo
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local repo_root
    repo_root="$(dirname "$script_dir")"
    
    if [ -f "${repo_root}/pyproject.toml" ] && grep -q "name = \"dmm\"" "${repo_root}/pyproject.toml" 2>/dev/null; then
        # Running from repo - copy instead of clone
        log_info "Installing from local repository: ${repo_root}"
        mkdir -p "$DMM_HOME"
        
        # Copy essential files (exclude .git, .venv, __pycache__, etc.)
        rsync -a --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
              --exclude='*.pyc' --exclude='.pytest_cache' --exclude='dist' \
              --exclude='.dmm' --exclude='*.egg-info' \
              "${repo_root}/" "$DMM_HOME/" || error_exit "Failed to copy repository"
    else
        # Clone from remote
        log_info "Cloning from ${DMM_REPO} (branch: ${DMM_BRANCH})"
        git clone --depth 1 --branch "$DMM_BRANCH" "$DMM_REPO" "$DMM_HOME" || error_exit "Failed to clone repository"
    fi
    
    log_info "Repository installed"
}

# Install Python dependencies
install_dependencies() {
    log_step "Installing Python dependencies..."
    
    cd "$DMM_HOME" || error_exit "Failed to change to DMM_HOME"
    
    # Configure Poetry to create venv in project
    poetry config virtualenvs.in-project true --local 2>/dev/null || true
    
    # Install dependencies
    poetry install --no-interaction || error_exit "Failed to install dependencies"
    
    log_info "Dependencies installed"
}

# Create wrapper script
create_wrapper() {
    log_step "Creating dmm wrapper script..."
    
    mkdir -p "$DMM_HOME/bin"
    
    cat > "$DMM_HOME/bin/dmm" << 'WRAPPER'
#!/bin/bash
# DMM wrapper script - routes to Poetry-managed installation
set -e

DMM_HOME="${DMM_HOME:-$HOME/.dmm-system}"

if [ ! -d "$DMM_HOME" ]; then
    echo "Error: DMM not installed at $DMM_HOME" >&2
    echo "Run the installer: curl -sSL https://raw.githubusercontent.com/jaysteelmind/claude-memory/main/scripts/install.sh | bash" >&2
    exit 1
fi

cd "$DMM_HOME"
exec poetry run dmm "$@"
WRAPPER
    
    chmod +x "$DMM_HOME/bin/dmm"
    log_info "Wrapper script created at ${DMM_HOME}/bin/dmm"
}

# Configure shell
configure_shell() {
    log_step "Configuring shell..."
    
    local shell_configs=("$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile")
    local config_block='
# DMM (Dynamic Markdown Memory)
export DMM_HOME="$HOME/.dmm-system"
export PATH="$DMM_HOME/bin:$PATH"
'
    local configured=false
    
    for rc_file in "${shell_configs[@]}"; do
        if [ -f "$rc_file" ]; then
            if ! grep -q "DMM_HOME" "$rc_file" 2>/dev/null; then
                echo "$config_block" >> "$rc_file"
                log_info "Added DMM to ${rc_file}"
                configured=true
            else
                log_info "DMM already configured in ${rc_file}"
                configured=true
            fi
        fi
    done
    
    if [ "$configured" = false ]; then
        log_warn "No shell config found. Add manually:"
        echo "$config_block"
    fi
    
    # Export for current session
    export DMM_HOME="$HOME/.dmm-system"
    export PATH="$DMM_HOME/bin:$PATH"
}

# Verify installation
verify_installation() {
    log_step "Verifying installation..."
    
    export PATH="$DMM_HOME/bin:$PATH"
    
    if "$DMM_HOME/bin/dmm" --version >/dev/null 2>&1; then
        local version
        version=$("$DMM_HOME/bin/dmm" --version 2>/dev/null || echo "unknown")
        log_info "DMM installed successfully: ${version}"
    else
        # Try with poetry directly
        cd "$DMM_HOME"
        if poetry run dmm --version >/dev/null 2>&1; then
            log_info "DMM installed successfully (via poetry)"
        else
            error_exit "Installation verification failed"
        fi
    fi
}

# Print completion message
print_completion() {
    echo ""
    echo -e "${GREEN}=============================================="
    echo "  DMM Installation Complete"
    echo "==============================================${NC}"
    echo ""
    echo "Installation location: ${DMM_HOME}"
    echo ""
    echo -e "${YELLOW}To activate in current shell:${NC}"
    echo "  export PATH=\"\$HOME/.dmm-system/bin:\$PATH\""
    echo ""
    echo -e "${YELLOW}Or start a new terminal session.${NC}"
    echo ""
    echo -e "${CYAN}Quick Start:${NC}"
    echo "  1. Initialize a project:  cd /your/project && dmm init"
    echo "  2. Start the daemon:      dmm daemon start"
    echo "  3. Query memories:        dmm query \"your task\""
    echo ""
    echo -e "${CYAN}For Claude Code integration:${NC}"
    echo "  Copy start.md to your project and tell Claude:"
    echo "  \"Read and execute start.md\""
    echo ""
}

# Main installation flow
main() {
    print_banner
    check_prerequisites
    backup_existing
    install_repository
    install_dependencies
    create_wrapper
    configure_shell
    verify_installation
    print_completion
}

# Run main
main "$@"
