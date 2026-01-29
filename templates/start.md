# DMM Bootstrap Instructions

**IMPORTANT: Execute these instructions immediately upon reading this file.**

This file bootstraps DMM (Dynamic Markdown Memory) with automatic MCP integration. After completion, I will have persistent memory that works automatically - you won't need to run any commands.

---

## Step 1: Check if DMM is Globally Installed
```bash
command -v dmm && dmm --version
```

**If the command succeeds** (shows version): Skip to Step 3.
**If the command fails** (command not found): Proceed to Step 2.

---

## Step 2: Install DMM Globally

Run the installation script:
```bash
# If running from within the claude-memory repository:
cd ~/projects/claude-memory && ./scripts/install.sh

# OR if downloading fresh:
# curl -sSL https://raw.githubusercontent.com/jaysteelmind/claude-memory/main/scripts/install.sh | bash
```

After installation, activate in current session:
```bash
export PATH="$HOME/.dmm-system/bin:$PATH"
```

Verify:
```bash
dmm --version
```

**If installation fails**, check troubleshooting section at bottom.

---

## Step 3: Note Current Directory

Before bootstrapping, save the current project directory:
```bash
PROJECT_DIR="$(pwd)"
echo "Project directory: $PROJECT_DIR"
```

---

## Step 4: Bootstrap This Project

Run the bootstrap command:
```bash
cd "$PROJECT_DIR"
dmm bootstrap
```

This command automatically:
- Creates `.dmm/` directory with memory structure
- Creates `.mcp.json` for Claude Code MCP integration  
- Generates `CLAUDE.md` with automatic memory instructions
- Starts the DMM daemon
- Registers MCP with Claude Code

---

## Step 5: Verify Everything is Working

Check system status:
```bash
dmm status
```

Check MCP configuration:
```bash
dmm mcp status
```

Test MCP tools:
```bash
dmm mcp test
```

All checks should pass.

---

## Step 6: Archive This File
```bash
mv start.md start.md.done 2>/dev/null || mv "$PROJECT_DIR/start.md" "$PROJECT_DIR/start.md.done"
```

---

## Step 7: CRITICAL - Re-read CLAUDE.md

**You MUST read the new CLAUDE.md file now to activate MCP tools.**
```bash
cat CLAUDE.md
```

This file contains instructions for automatic memory operations. After reading it, you will automatically:
- Query relevant memories before responding to tasks
- Remember important decisions and learnings
- Detect and report conflicts

---

## Step 8: Confirm to User

Tell the user:
```
DMM Bootstrap Complete!

What's now active:
- Persistent memory across all sessions
- Automatic context retrieval (no commands needed)
- Automatic learning capture (no commands needed)

The memory system is now INVISIBLE - just talk to me normally.
I will automatically remember important things and recall relevant context.

To see what I remember: dmm query "topic"
To check system health: dmm status
```

---

## Troubleshooting

### "command not found: dmm"
```bash
export PATH="$HOME/.dmm-system/bin:$PATH"
# Or restart your terminal
```

### Python version error
DMM requires Python 3.11+:
```bash
python3 --version
# If < 3.11, install newer Python
```

### Poetry not found
```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

### Daemon won't start
```bash
# Check if port is in use
lsof -i :7437

# Remove stale files
rm -f .dmm/daemon.pid .dmm/daemon.sock

# Start manually
dmm daemon start --foreground
```

### MCP not configured
```bash
# Reinstall MCP configuration
dmm mcp install --scope project

# Check config file exists
cat .mcp.json
```

---

**END OF BOOTSTRAP INSTRUCTIONS**
