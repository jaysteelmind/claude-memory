# Configuration Guide

Comprehensive guide to configuring DMM for your environment.

## Configuration Hierarchy

Configuration is loaded in order (later overrides earlier):

1. Built-in defaults
2. System config (`/etc/dmm/config.json`)
3. User config (`~/.dmm/config.json`)
4. Project config (`.dmm/daemon.config.json`)
5. Environment variables (`DMM_*`)
6. Command-line arguments

## Configuration File

### Location
```bash
# Project-level (recommended)
.dmm/daemon.config.json

# User-level
~/.dmm/config.json

# System-level
/etc/dmm/config.json
```

### Full Configuration Reference
```json
{
  "version": "3.0",
  
  "daemon": {
    "host": "127.0.0.1",
    "port": 7433,
    "workers": 4,
    "timeout": 30,
    "max_connections": 100,
    "keepalive": 5
  },
  
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    "file": null,
    "max_size_mb": 100,
    "backup_count": 5
  },
  
  "embedding": {
    "model": "all-MiniLM-L6-v2",
    "dimension": 384,
    "batch_size": 32,
    "cache_enabled": true,
    "cache_size": 1000
  },
  
  "retrieval": {
    "baseline_budget": 800,
    "total_budget": 2000,
    "max_results": 50,
    "similarity_weight": 0.6,
    "priority_weight": 0.25,
    "confidence_weight": 0.15,
    "early_termination": true,
    "min_similarity": 0.3
  },
  
  "graph": {
    "enabled": true,
    "database": "knowledge.kuzu",
    "max_depth": 2,
    "vector_weight": 0.6,
    "graph_weight": 0.4,
    "boost_per_connection": 0.2,
    "decay_per_hop": 0.5
  },
  
  "memory": {
    "min_tokens": 300,
    "max_tokens": 800,
    "default_priority": 0.5,
    "default_confidence": "active",
    "stale_threshold_days": 30
  },
  
  "write_back": {
    "require_review": true,
    "auto_index": true,
    "quality_checks": {
      "min_tokens": 100,
      "max_tokens": 1000,
      "require_tags": true,
      "min_tags": 1,
      "max_tags": 10,
      "require_title": true
    }
  },
  
  "conflicts": {
    "scan_on_index": true,
    "tag_overlap_threshold": 0.7,
    "semantic_threshold": 0.85,
    "auto_resolve": false
  },
  
  "agentos": {
    "skills_dir": "skills",
    "tools_dir": "tools",
    "agents_dir": "agents",
    "tasks_dir": "tasks",
    "max_concurrent_tasks": 5,
    "task_timeout": 300,
    "enable_self_mod": false,
    "self_mod_approval_level": 3
  },
  
  "security": {
    "allowed_paths": ["/home/user/project"],
    "blocked_paths": ["/etc", "/root"],
    "max_file_size_mb": 10,
    "allowed_extensions": [".py", ".md", ".yaml", ".json"]
  }
}
```

## Section Details

### Daemon Configuration
```json
{
  "daemon": {
    "host": "127.0.0.1",    // Bind address
    "port": 7433,            // Listen port
    "workers": 4,            // Worker processes
    "timeout": 30,           // Request timeout (seconds)
    "max_connections": 100,  // Max concurrent connections
    "keepalive": 5           // Keepalive timeout (seconds)
  }
}
```

**Environment Variables:**
```bash
DMM_HOST=0.0.0.0
DMM_PORT=8080
DMM_WORKERS=8
```

### Logging Configuration
```json
{
  "logging": {
    "level": "INFO",           // DEBUG, INFO, WARNING, ERROR
    "format": "...",           // Log format string
    "file": "/var/log/dmm.log", // Log file (null for stdout)
    "max_size_mb": 100,        // Max log file size
    "backup_count": 5          // Rotated file count
  }
}
```

**Log Levels:**
| Level | Use Case |
|-------|----------|
| DEBUG | Development, troubleshooting |
| INFO | Normal operation |
| WARNING | Issues that don't stop operation |
| ERROR | Failures requiring attention |

### Embedding Configuration
```json
{
  "embedding": {
    "model": "all-MiniLM-L6-v2",  // Sentence transformer model
    "dimension": 384,              // Must match model output
    "batch_size": 32,              // Embeddings per batch
    "cache_enabled": true,         // Cache embeddings
    "cache_size": 1000             // LRU cache size
  }
}
```

**Supported Models:**
| Model | Dimension | Speed | Quality |
|-------|-----------|-------|---------|
| all-MiniLM-L6-v2 | 384 | Fast | Good |
| all-mpnet-base-v2 | 768 | Medium | Better |
| all-MiniLM-L12-v2 | 384 | Medium | Better |

### Retrieval Configuration
```json
{
  "retrieval": {
    "baseline_budget": 800,     // Tokens for baseline memories
    "total_budget": 2000,       // Total token budget
    "max_results": 50,          // Max memories to consider
    "similarity_weight": 0.6,   // Weight for similarity score
    "priority_weight": 0.25,    // Weight for priority
    "confidence_weight": 0.15,  // Weight for confidence
    "early_termination": true,  // Stop when budget filled
    "min_similarity": 0.3       // Minimum similarity threshold
  }
}
```

**Scoring Formula:**
```
final_score = similarity_weight × similarity 
            + priority_weight × priority 
            + confidence_weight × confidence_score
```

### Graph Configuration
```json
{
  "graph": {
    "enabled": true,           // Enable knowledge graph
    "database": "knowledge.kuzu",
    "max_depth": 2,            // Max traversal depth
    "vector_weight": 0.6,      // Weight for vector score
    "graph_weight": 0.4,       // Weight for graph score
    "boost_per_connection": 0.2,
    "decay_per_hop": 0.5
  }
}
```

### Memory Configuration
```json
{
  "memory": {
    "min_tokens": 300,           // Minimum memory size
    "max_tokens": 800,           // Maximum memory size
    "default_priority": 0.5,     // Default priority for new memories
    "default_confidence": "active",
    "stale_threshold_days": 30   // Days until stale
  }
}
```

### Write-Back Configuration
```json
{
  "write_back": {
    "require_review": true,      // Require review for new memories
    "auto_index": true,          // Index after commit
    "quality_checks": {
      "min_tokens": 100,
      "max_tokens": 1000,
      "require_tags": true,
      "min_tags": 1,
      "max_tags": 10,
      "require_title": true
    }
  }
}
```

### AgentOS Configuration
```json
{
  "agentos": {
    "skills_dir": "skills",
    "tools_dir": "tools",
    "agents_dir": "agents",
    "tasks_dir": "tasks",
    "max_concurrent_tasks": 5,
    "task_timeout": 300,
    "enable_self_mod": false,
    "self_mod_approval_level": 3
  }
}
```

**Self-Modification Levels:**
| Level | Description | Approval |
|-------|-------------|----------|
| 1 | Memory updates | Automatic |
| 2 | Skill changes | Logged |
| 3 | Behavior changes | Human required |
| 4 | Goal changes | Human required |

### Security Configuration
```json
{
  "security": {
    "allowed_paths": [
      "/home/user/project",
      "/opt/data"
    ],
    "blocked_paths": [
      "/etc",
      "/root",
      "**/.git/**"
    ],
    "max_file_size_mb": 10,
    "allowed_extensions": [
      ".py", ".md", ".yaml", ".json", ".txt"
    ]
  }
}
```

## Environment Variables

All configuration can be overridden via environment variables:
```bash
# Pattern: DMM_<SECTION>_<KEY>=value

# Daemon
export DMM_DAEMON_HOST=0.0.0.0
export DMM_DAEMON_PORT=8080

# Logging
export DMM_LOGGING_LEVEL=DEBUG
export DMM_LOGGING_FILE=/var/log/dmm.log

# Embedding
export DMM_EMBEDDING_MODEL=all-mpnet-base-v2

# Retrieval
export DMM_RETRIEVAL_TOTAL_BUDGET=4000

# Graph
export DMM_GRAPH_ENABLED=false

# Shorthand (common settings)
export DMM_LOG_LEVEL=INFO
export DMM_HOST=127.0.0.1
export DMM_PORT=7433
```

## Profile-Based Configuration

Create profiles for different environments:
```bash
# .dmm/profiles/development.json
{
  "logging": {"level": "DEBUG"},
  "daemon": {"workers": 1}
}

# .dmm/profiles/production.json
{
  "logging": {"level": "INFO", "file": "/var/log/dmm.log"},
  "daemon": {"workers": 8}
}

# Use profile
DMM_PROFILE=production dmm daemon start
```

## Configuration Validation
```bash
# Validate configuration
dmm config validate

# Show effective configuration
dmm config show

# Show specific section
dmm config show --section retrieval
```

## Common Configurations

### High-Performance Setup
```json
{
  "daemon": {
    "workers": 8,
    "max_connections": 500
  },
  "embedding": {
    "batch_size": 64,
    "cache_size": 5000
  },
  "retrieval": {
    "early_termination": true,
    "max_results": 100
  }
}
```

### Memory-Constrained Setup
```json
{
  "daemon": {
    "workers": 2,
    "max_connections": 50
  },
  "embedding": {
    "model": "all-MiniLM-L6-v2",
    "cache_size": 100
  },
  "retrieval": {
    "total_budget": 1000,
    "max_results": 20
  }
}
```

### Secure Setup
```json
{
  "daemon": {
    "host": "127.0.0.1"
  },
  "security": {
    "allowed_paths": ["/opt/project"],
    "blocked_paths": ["**/*secret*", "**/.env"]
  },
  "agentos": {
    "enable_self_mod": false
  }
}
```

## See Also

- [Deployment Guide](deployment.md)
- [Security Guide](security.md)
- [CLI Reference](../CLI_REFERENCE.md)
