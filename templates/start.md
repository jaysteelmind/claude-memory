# DMM Bootstrap Instructions

**IMPORTANT: Execute these instructions immediately upon reading this file.**

This file bootstraps DMM (Dynamic Markdown Memory) for this project. Follow each step in sequence.

---

## Step 1: Check if DMM is Globally Installed

Run this command to check if DMM is available:
```bash
command -v dmm && dmm --version
```

**If the command succeeds:** Skip to Step 3.

**If the command fails (command not found):** Proceed to Step 2.

---

## Step 2: Install DMM Globally

DMM needs to be installed globally at `~/.dmm-system`.

**Option A: Clone and install (Recommended)**
```bash
git clone https://github.com/jaysteelmind/claude-memory.git ~/projects/claude-memory
cd ~/projects/claude-memory
./scripts/install.sh
```

**Option B: If repository already exists locally**
```bash
cd ~/projects/claude-memory
./scripts/install.sh
```

After installation, ensure PATH is updated:
```bash
export PATH="$HOME/.dmm-system/bin:$PATH"
```

Verify installation:
```bash
dmm --version
```

---

## Step 3: Initialize DMM in This Project

Check if `.dmm` directory exists:
```bash
ls -la .dmm 2>/dev/null || echo "DMM not initialized"
```

**If `.dmm` exists:** Skip to Step 4.

**If `.dmm` does not exist:** Initialize DMM:
```bash
dmm init
```

---

## Step 4: Start the DMM Daemon

Check if daemon is running:
```bash
dmm daemon status
```

**If daemon is running:** Skip to Step 5.

**If daemon is not running:** Start it:
```bash
dmm daemon start
```

Wait for daemon to be ready:
```bash
for i in {1..30}; do
    dmm daemon status 2>/dev/null && break
    sleep 1
done
```

---

## Step 5: Verify System Health

Run the full system check:
```bash
dmm status
```

Expected output should show:
- Daemon: running
- Indexed memories count
- Baseline files and tokens

---

## Step 6: Archive This File

Bootstrap is complete. Archive this file to prevent re-execution:
```bash
mv start.md start.md.done
```

---

## Step 7: Confirm Completion

Report to the user:
```
DMM Bootstrap Complete!

System Status:
- DMM installed at: ~/.dmm-system
- Project initialized: .dmm/
- Daemon: running

You can now use DMM commands:
- dmm query "your task" - Get relevant context
- dmm status - Check system health
- dmm write propose - Create new memories

For operational guidelines, see: .dmm/BOOT.md
```

---

## Troubleshooting

### Daemon fails to start
```bash
# Check for port conflicts
lsof -i :7433

# Remove stale PID file
rm -f /tmp/dmm.pid

# Try foreground mode for debugging
dmm daemon start --foreground
```

### Permission denied errors
```bash
# Ensure scripts are executable
chmod +x ~/.dmm-system/bin/dmm
chmod +x ~/.dmm-system/scripts/*.sh
```

### Python version issues

DMM requires Python 3.11+. Check version:
```bash
python3 --version
```

---

**END OF BOOTSTRAP INSTRUCTIONS**
