# Deployment Guide

Deploy DMM in production environments.

## Deployment Options

| Option | Best For | Complexity |
|--------|----------|------------|
| Local | Development, single user | Low |
| Docker | Isolated environments | Medium |
| Systemd | Linux servers | Medium |
| Kubernetes | Scalable production | High |

## Local Development

### Quick Start
```bash
# Clone and install
git clone https://github.com/anthropic/claude-memory.git
cd claude-memory
poetry install

# Initialize
poetry run dmm init

# Start daemon
poetry run dmm daemon start

# Verify
poetry run dmm status
```

### Development Mode
```bash
# Run with hot reload
poetry run dmm daemon start --dev

# Enable debug logging
DMM_LOG_LEVEL=DEBUG poetry run dmm daemon start
```

## Docker Deployment

### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry

# Copy project files
COPY pyproject.toml poetry.lock ./
COPY src/ ./src/
COPY CLAUDE.md ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction

# Create data directories
RUN mkdir -p /data/.dmm

# Environment
ENV DMM_HOME=/data/.dmm
ENV DMM_HOST=0.0.0.0
ENV DMM_PORT=7433

# Expose port
EXPOSE 7433

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:7433/health || exit 1

# Start daemon
CMD ["dmm", "daemon", "start", "--foreground"]
```

### Docker Compose
```yaml
# docker-compose.yml
version: '3.8'

services:
  dmm:
    build: .
    ports:
      - "7433:7433"
    volumes:
      - dmm-data:/data/.dmm
      - ./project:/app/project:ro
    environment:
      - DMM_LOG_LEVEL=INFO
      - DMM_EMBEDDING_MODEL=all-MiniLM-L6-v2
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7433/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  dmm-data:
```

### Running with Docker
```bash
# Build
docker-compose build

# Start
docker-compose up -d

# Check logs
docker-compose logs -f dmm

# Stop
docker-compose down
```

## Systemd Service

### Service File
```ini
# /etc/systemd/system/dmm.service
[Unit]
Description=DMM Dynamic Markdown Memory Service
After=network.target

[Service]
Type=simple
User=dmm
Group=dmm
WorkingDirectory=/opt/dmm
Environment=DMM_HOME=/var/lib/dmm
Environment=DMM_LOG_LEVEL=INFO
ExecStart=/opt/dmm/.venv/bin/dmm daemon start --foreground
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=10

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/dmm /var/log/dmm
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### Installation
```bash
# Create user
sudo useradd -r -s /bin/false dmm

# Create directories
sudo mkdir -p /opt/dmm /var/lib/dmm /var/log/dmm
sudo chown dmm:dmm /var/lib/dmm /var/log/dmm

# Install application
sudo cp -r . /opt/dmm/
cd /opt/dmm
sudo -u dmm python -m venv .venv
sudo -u dmm .venv/bin/pip install poetry
sudo -u dmm .venv/bin/poetry install

# Install service
sudo cp dmm.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dmm
sudo systemctl start dmm

# Check status
sudo systemctl status dmm
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DMM_HOME` | `.dmm` | Data directory path |
| `DMM_HOST` | `127.0.0.1` | Daemon bind address |
| `DMM_PORT` | `7433` | Daemon port |
| `DMM_LOG_LEVEL` | `INFO` | Log level |
| `DMM_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `DMM_BASELINE_BUDGET` | `800` | Baseline token budget |
| `DMM_TOTAL_BUDGET` | `2000` | Total token budget |

### Configuration File
```json
// .dmm/daemon.config.json
{
  "host": "127.0.0.1",
  "port": 7433,
  "log_level": "INFO",
  "embedding": {
    "model": "all-MiniLM-L6-v2",
    "dimension": 384
  },
  "retrieval": {
    "baseline_budget": 800,
    "total_budget": 2000,
    "similarity_weight": 0.6,
    "priority_weight": 0.25,
    "confidence_weight": 0.15
  },
  "graph": {
    "enabled": true,
    "max_depth": 2,
    "vector_weight": 0.6
  },
  "daemon": {
    "workers": 4,
    "timeout": 30,
    "max_connections": 100
  }
}
```

## Performance Tuning

### Memory Optimization
```json
{
  "embedding": {
    "batch_size": 32,
    "cache_size": 1000
  },
  "retrieval": {
    "max_results": 50,
    "early_termination": true
  }
}
```

### Database Optimization
```bash
# Optimize SQLite
sqlite3 .dmm/index/embeddings.db "VACUUM;"
sqlite3 .dmm/index/embeddings.db "ANALYZE;"

# Set journal mode
sqlite3 .dmm/index/embeddings.db "PRAGMA journal_mode=WAL;"
```

### Connection Pooling
```json
{
  "database": {
    "pool_size": 10,
    "max_overflow": 20,
    "pool_timeout": 30
  }
}
```

## Monitoring

### Health Endpoint
```bash
curl http://localhost:7433/health
```

Response:
```json
{
  "status": "healthy",
  "version": "3.0.0",
  "uptime_seconds": 3600,
  "memory_count": 150,
  "index_size_mb": 12.5,
  "graph_nodes": 200,
  "graph_edges": 450
}
```

### Metrics Endpoint
```bash
curl http://localhost:7433/metrics
```

### Log Aggregation
```yaml
# fluent-bit config
[INPUT]
    Name tail
    Path /var/log/dmm/*.log
    Tag dmm.*

[OUTPUT]
    Name elasticsearch
    Match dmm.*
    Host elasticsearch
    Port 9200
    Index dmm-logs
```

## Backup and Recovery

### Backup Script
```bash
#!/bin/bash
# backup-dmm.sh

BACKUP_DIR="/backup/dmm/$(date +%Y%m%d)"
DMM_HOME="/var/lib/dmm"

mkdir -p "$BACKUP_DIR"

# Stop daemon
systemctl stop dmm

# Backup databases
cp "$DMM_HOME/index/embeddings.db" "$BACKUP_DIR/"
cp -r "$DMM_HOME/index/knowledge.kuzu" "$BACKUP_DIR/"

# Backup memories
tar -czf "$BACKUP_DIR/memory.tar.gz" -C "$DMM_HOME" memory/

# Backup configuration
cp "$DMM_HOME/daemon.config.json" "$BACKUP_DIR/"

# Start daemon
systemctl start dmm

echo "Backup complete: $BACKUP_DIR"
```

### Recovery
```bash
#!/bin/bash
# restore-dmm.sh

BACKUP_DIR="$1"
DMM_HOME="/var/lib/dmm"

if [ -z "$BACKUP_DIR" ]; then
    echo "Usage: restore-dmm.sh <backup_dir>"
    exit 1
fi

# Stop daemon
systemctl stop dmm

# Restore databases
cp "$BACKUP_DIR/embeddings.db" "$DMM_HOME/index/"
cp -r "$BACKUP_DIR/knowledge.kuzu" "$DMM_HOME/index/"

# Restore memories
tar -xzf "$BACKUP_DIR/memory.tar.gz" -C "$DMM_HOME"

# Restore configuration
cp "$BACKUP_DIR/daemon.config.json" "$DMM_HOME/"

# Start daemon
systemctl start dmm

# Verify
dmm status
```

## Security

### Network Security
```bash
# Bind only to localhost
DMM_HOST=127.0.0.1 dmm daemon start

# Use reverse proxy for external access
# nginx config:
location /dmm/ {
    proxy_pass http://127.0.0.1:7433/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    
    # Authentication
    auth_basic "DMM";
    auth_basic_user_file /etc/nginx/.htpasswd;
}
```

### File Permissions
```bash
# Secure permissions
chmod 700 /var/lib/dmm
chmod 600 /var/lib/dmm/daemon.config.json
chmod 600 /var/lib/dmm/index/*.db
```

### Secrets Management

Never store secrets in memory files. Use environment variables:
```bash
# Bad
echo "api_key: sk-12345" >> .dmm/memory/project/config.md

# Good
export DMM_API_KEY=sk-12345
```

## Troubleshooting

### Daemon Won't Start
```bash
# Check port availability
lsof -i :7433

# Check permissions
ls -la /var/lib/dmm

# Check logs
journalctl -u dmm -f
```

### Performance Issues
```bash
# Check memory usage
dmm status --verbose

# Optimize index
dmm reindex --optimize

# Check slow queries
DMM_LOG_LEVEL=DEBUG dmm query "test"
```

### Data Corruption
```bash
# Verify integrity
sqlite3 .dmm/index/embeddings.db "PRAGMA integrity_check;"

# Rebuild if needed
dmm reindex --full --force
```

## See Also

- [Configuration Guide](configuration.md)
- [Security Guide](security.md)
- [Troubleshooting Guide](../TROUBLESHOOTING.md)
