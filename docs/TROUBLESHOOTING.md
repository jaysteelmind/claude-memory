# DMM Troubleshooting Guide

Common issues and solutions for the Dynamic Markdown Memory system.

## Daemon Issues

### Daemon won't start

**Symptom**: `dmm daemon start` fails or daemon exits immediately.

**Solutions**:

1. **Port already in use**
```bash
   # Check if port is in use
   lsof -i :7433
   
   # Use a different port
   dmm daemon start --port 7434
```

2. **Stale PID file**
```bash
   # Remove stale PID file
   rm /tmp/dmm.pid
   
   # Try starting again
   dmm daemon start
```

3. **Check logs in foreground mode**
```bash
   dmm daemon start --foreground
```

### Cannot connect to daemon

**Symptom**: `dmm query` or `dmm status` reports connection error.

**Solutions**:

1. **Verify daemon is running**
```bash
   dmm daemon status
   
   # Or check process directly
   ps aux | grep dmm
```

2. **Check correct host/port**
```bash
   # Default is 127.0.0.1:7433
   dmm status --host 127.0.0.1 --port 7433
```

3. **Firewall issues**
```bash
   # Ensure localhost connections are allowed
   curl http://127.0.0.1:7433/health
```

### Daemon crashes on query

**Symptom**: Daemon exits when processing a query.

**Solutions**:

1. **Check for CUDA/GPU issues**
   
   If using a GPU with incompatible drivers, the embedding model may crash.
   The system defaults to CPU, but verify:
```python
   # In Python, verify device
   from dmm.indexer.embedder import MemoryEmbedder
   embedder = MemoryEmbedder()
   print(embedder.get_model_info())
```

2. **Memory exhaustion**
   
   Large memory collections may exhaust RAM when loading the model:
```bash
   # Check available memory
   free -h
   
   # Monitor during startup
   watch -n 1 free -h
```

---

## Indexing Issues

### Files not being indexed

**Symptom**: New memory files don't appear in query results.

**Solutions**:

1. **Verify file location**
```bash
   # Files must be in .dmm/memory/{scope}/
   ls -la .dmm/memory/
```

2. **Check file extension**
   
   Only `.md` files are indexed.

3. **Trigger manual reindex**
```bash
   dmm reindex
```

4. **Check for parse errors**
```bash
   dmm validate --path .dmm/memory/project/myfile.md
```

5. **Verify watcher is active**
```bash
   dmm status
   # Look for "Watcher: active"
```

### Parse errors

**Symptom**: `dmm validate` reports errors.

**Solutions**:

1. **Check YAML syntax**
```bash
   # Common issues:
   # - Missing quotes around strings with special chars
   # - Incorrect indentation
   # - Missing colons
   
   # Validate YAML separately
   python3 -c "import yaml; yaml.safe_load(open('.dmm/memory/project/file.md'))"
```

2. **Verify required fields**
```yaml
   # All these are required:
   id: mem_YYYY_MM_DD_NNN
   tags: [tag1, tag2]
   scope: project  # baseline|global|agent|project|ephemeral
   priority: 0.5   # 0.0 to 1.0
   confidence: active  # experimental|active|stable|deprecated
   status: active  # active|deprecated
```

3. **Check enum values**
```bash
   # scope must be one of: baseline, global, agent, project, ephemeral
   # confidence must be one of: experimental, active, stable, deprecated
   # status must be one of: active, deprecated
```

### Token count warnings

**Symptom**: "Token count below recommended minimum" warning.

**Solutions**:

1. **Expand content**
   
   Memories should be 300-800 tokens. Add more context:
   - Background information
   - Rationale for decisions
   - Examples
   - Implementation details

2. **Ignore if appropriate**
   
   Warnings don't prevent indexing. Small memories work fine.

---

## Query Issues

### No results returned

**Symptom**: Query returns empty or only baseline.

**Solutions**:

1. **Verify memories are indexed**
```bash
   dmm status
   # Check "Indexed: N memories"
```

2. **Try broader query**
```bash
   # More general terms
   dmm query "authentication" --verbose
```

3. **Check scope filter**
```bash
   # Remove scope filter
   dmm query "my topic"  # without --scope
```

4. **Increase budget**
```bash
   dmm query "my topic" --budget 3000
```

### Irrelevant results

**Symptom**: Retrieved memories don't match the query.

**Solutions**:

1. **Use more specific query**
```bash
   # Bad: "help"
   # Good: "JWT token authentication implementation"
```

2. **Check memory tags**
   
   Ensure memories have relevant tags that match query terms.

3. **Reindex after tag changes**
```bash
   dmm reindex
```

### Baseline not appearing

**Symptom**: Baseline memories missing from results.

**Solutions**:

1. **Verify baseline scope**
```bash
   # Check the scope field in frontmatter
   grep -r "scope: baseline" .dmm/memory/baseline/
```

2. **Check file location**
```bash
   # Baseline files must be in .dmm/memory/baseline/
   ls -la .dmm/memory/baseline/
```

3. **Verify status is active**
```yaml
   # In frontmatter:
   status: active  # not deprecated
```

---

## Performance Issues

### Slow startup

**Symptom**: Daemon takes long time to start.

**Causes and Solutions**:

1. **First run downloading model**
   
   The embedding model (~90MB) downloads on first use:
```bash
   # Pre-download the model
   python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

2. **Large memory collection**
   
   Full reindex happens on startup:
```bash
   # Check file count
   find .dmm/memory -name "*.md" | wc -l
```

### Slow queries

**Symptom**: Queries take more than 200ms.

**Solutions**:

1. **Check memory count**
   
   Performance degrades with very large collections (>1000 memories).

2. **Reduce budget**
```bash
   dmm query "topic" --budget 1000
```

3. **Use scope filter**
```bash
   dmm query "topic" --scope project
```

### High memory usage

**Symptom**: Process using excessive RAM.

**Solutions**:

1. **Check baseline**
   
   The embedding model uses ~500MB. This is expected.

2. **Reduce collection size**
   
   Archive old memories to `.dmm/memory/deprecated/`.

---

## Database Issues

### Corrupted database

**Symptom**: Errors mentioning SQLite or database corruption.

**Solutions**:

1. **Delete and rebuild**
```bash
   rm .dmm/index/embeddings.db
   dmm reindex
```

2. **Check disk space**
```bash
   df -h .
```

### Database locked

**Symptom**: "database is locked" errors.

**Solutions**:

1. **Stop all daemon instances**
```bash
   pkill -f "dmm"
   rm /tmp/dmm*.pid
```

2. **Check for multiple processes**
```bash
   ps aux | grep dmm
```

---

## CLI Issues

### Command not found

**Symptom**: `dmm: command not found`

**Solutions**:

1. **Activate virtual environment**
```bash
   poetry shell
   # or
   source .venv/bin/activate
```

2. **Use poetry run**
```bash
   poetry run dmm --help
```

3. **Install globally**
```bash
   pip install .
```

### Import errors

**Symptom**: Python import errors when running dmm.

**Solutions**:

1. **Reinstall dependencies**
```bash
   poetry install
```

2. **Check Python version**
```bash
   python3 --version
   # Requires 3.11+
```

---

## Getting Help

If issues persist:

1. **Run with verbose output**
```bash
   dmm daemon start --foreground
   dmm query "test" --verbose
```

2. **Check logs**
```bash
   # Daemon logs to stdout in foreground mode
```

3. **Validate configuration**
```bash
   cat .dmm/daemon.config.json | python3 -m json.tool
```

4. **Run tests**
```bash
   poetry run pytest tests/ -v
```

5. **Report issues**
   
   Include:
   - DMM version
   - Python version
   - Operating system
   - Error messages
   - Steps to reproduce
