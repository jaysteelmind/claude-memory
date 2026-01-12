# DMM CLI Reference

Complete reference for all DMM command-line interface commands.

## Global Options

All commands support these global options:

| Option | Description |
|--------|-------------|
| `--help` | Show help message and exit |
| `--install-completion` | Install shell completion |
| `--show-completion` | Show shell completion script |

---

## dmm init

Initialize DMM in the current directory.

### Usage
```bash
dmm init [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--force` | flag | false | Overwrite existing .dmm directory |

### Examples
```bash
# Initialize new project
dmm init

# Reinitialize existing project
dmm init --force
```

### Created Structure
```
.dmm/
  BOOT.md
  policy.md
  daemon.config.json
  index/
  memory/
    baseline/
      identity.md
    global/
    agent/
    project/
    ephemeral/
    deprecated/
  packs/
```

---

## dmm daemon

Daemon management commands.

### dmm daemon start

Start the DMM daemon.
```bash
dmm daemon start [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--foreground, -f` | flag | false | Run in foreground (blocking) |
| `--host` | string | 127.0.0.1 | Daemon host address |
| `--port` | int | 7433 | Daemon port |
| `--pid-file` | path | /tmp/dmm.pid | PID file location |
```bash
# Start in background
dmm daemon start

# Start in foreground for debugging
dmm daemon start --foreground

# Custom port
dmm daemon start --port 8080
```

### dmm daemon stop

Stop the DMM daemon.
```bash
dmm daemon stop [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--pid-file` | path | /tmp/dmm.pid | PID file location |
| `--timeout` | float | 5.0 | Shutdown timeout in seconds |
```bash
# Normal stop
dmm daemon stop

# With extended timeout
dmm daemon stop --timeout 10
```

### dmm daemon status

Check daemon status.
```bash
dmm daemon status [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | string | 127.0.0.1 | Daemon host |
| `--port` | int | 7433 | Daemon port |
| `--pid-file` | path | /tmp/dmm.pid | PID file location |
| `--json` | flag | false | Output as JSON |
```bash
# Check status
dmm daemon status

# JSON output for scripting
dmm daemon status --json
```

### dmm daemon restart

Restart the DMM daemon.
```bash
dmm daemon restart [OPTIONS]
```

Options are the same as `daemon start`.

---

## dmm query

Query the memory system for relevant context.

### Usage
```bash
dmm query QUERY [OPTIONS]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `QUERY` | Yes | Task or question to query for |

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--budget, -b` | int | 2000 | Total token budget |
| `--baseline-budget` | int | 800 | Baseline token budget |
| `--scope, -s` | string | None | Filter by scope |
| `--exclude-ephemeral` | flag | false | Exclude ephemeral memories |
| `--include-deprecated` | flag | false | Include deprecated memories |
| `--output, -o` | path | None | Save pack to file |
| `--verbose, -v` | flag | false | Include scores and stats |
| `--host` | string | 127.0.0.1 | Daemon host |
| `--port` | int | 7433 | Daemon port |
| `--raw` | flag | false | Output raw markdown |

### Examples
```bash
# Basic query
dmm query "implement user authentication"

# With custom budget
dmm query "debug database issue" --budget 1500

# Filter to project scope only
dmm query "API design patterns" --scope project

# Verbose output with statistics
dmm query "system architecture" --verbose

# Save to file
dmm query "deployment process" --output context.md

# Raw markdown output
dmm query "coding standards" --raw
```

### Output

Returns a Memory Pack containing:
- Baseline entries (always included)
- Retrieved entries (ranked by relevance)
- Token statistics
- File paths for traceability

---

## dmm status

Show system status.

### Usage
```bash
dmm status [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | string | 127.0.0.1 | Daemon host |
| `--port` | int | 7433 | Daemon port |
| `--json` | flag | false | Output as JSON |

### Examples
```bash
# Show status
dmm status

# JSON output
dmm status --json
```

### Output
```
DMM Status
------------------------------
Daemon:          running (PID: 12345)
Memory root:     /path/to/.dmm/memory
Indexed:         42 memories
Baseline:        4 files, 650 tokens
Last reindex:    2025-01-11T14:30:00
Watcher:         active
```

---

## dmm reindex

Trigger reindexing of memory files.

### Usage
```bash
dmm reindex [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--full` | flag | true | Force full reindex |
| `--host` | string | 127.0.0.1 | Daemon host |
| `--port` | int | 7433 | Daemon port |

### Examples
```bash
# Full reindex
dmm reindex

# Reindex with custom daemon
dmm reindex --host localhost --port 8080
```

---

## dmm validate

Validate memory files.

### Usage
```bash
dmm validate [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--fix` | flag | false | Auto-fix where possible |
| `--path` | path | None | Validate specific file |

### Examples
```bash
# Validate all memory files
dmm validate

# Validate specific file
dmm validate --path .dmm/memory/project/auth.md
```

### Validation Checks

- Required frontmatter fields present
- Field values are valid
- Token count within range (300-800 recommended)
- H1 title present
- Ephemeral memories have expiry date

---

## dmm dirs

List memory directories.

### Usage
```bash
dmm dirs [OPTIONS]
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--host` | string | 127.0.0.1 | Daemon host |
| `--port` | int | 7433 | Daemon port |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DMM_HOST` | Default daemon host |
| `DMM_PORT` | Default daemon port |
| `DMM_PID_FILE` | Default PID file location |
