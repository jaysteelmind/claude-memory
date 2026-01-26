# Security Guide

Security best practices for DMM deployments.

## Security Model

DMM operates with a defense-in-depth approach:
```
┌─────────────────────────────────────────────┐
│              Network Security               │
│  ├─ Bind to localhost by default            │
│  └─ Reverse proxy for external access       │
├─────────────────────────────────────────────┤
│              Access Control                 │
│  ├─ Path allowlists/blocklists              │
│  └─ File extension filtering                │
├─────────────────────────────────────────────┤
│              Data Protection                │
│  ├─ No secrets in memory files              │
│  └─ Secure file permissions                 │
├─────────────────────────────────────────────┤
│              Agent Safety                   │
│  ├─ Self-modification levels                │
│  └─ Resource quotas                         │
└─────────────────────────────────────────────┘
```

## Network Security

### Default Configuration

DMM binds to localhost by default:
```json
{
  "daemon": {
    "host": "127.0.0.1",
    "port": 7433
  }
}
```

**Never expose DMM directly to the internet.**

### Reverse Proxy Setup

For external access, use a reverse proxy with authentication:
```nginx
# /etc/nginx/sites-available/dmm
server {
    listen 443 ssl;
    server_name dmm.example.com;
    
    ssl_certificate /etc/ssl/certs/dmm.crt;
    ssl_certificate_key /etc/ssl/private/dmm.key;
    
    # Strong SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    
    location / {
        # Authentication
        auth_basic "DMM Access";
        auth_basic_user_file /etc/nginx/.htpasswd;
        
        # Proxy to DMM
        proxy_pass http://127.0.0.1:7433;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_read_timeout 300s;
    }
}
```

### Firewall Rules
```bash
# Allow only local access
sudo ufw allow from 127.0.0.1 to any port 7433

# If using reverse proxy, allow nginx
sudo ufw allow 'Nginx Full'
```

## Access Control

### Path Restrictions

Configure allowed and blocked paths:
```json
{
  "security": {
    "allowed_paths": [
      "/home/user/projects",
      "/opt/data"
    ],
    "blocked_paths": [
      "/etc",
      "/root",
      "/var",
      "**/.git/**",
      "**/.env",
      "**/*secret*",
      "**/*password*",
      "**/*.key",
      "**/*.pem"
    ]
  }
}
```

### File Extension Filtering

Limit file types that can be indexed:
```json
{
  "security": {
    "allowed_extensions": [
      ".md",
      ".txt",
      ".yaml",
      ".json",
      ".py"
    ],
    "max_file_size_mb": 10
  }
}
```

### Path Validation

DMM validates all paths:
```python
from dmm.agentos.runtime import SafetyManager

safety = SafetyManager()

# Add rules
safety.add_path_rule("allow", "/home/user/project/**")
safety.add_path_rule("deny", "**/.env")
safety.add_path_rule("deny", "**/*secret*")

# Check path
if safety.check_path("/home/user/project/src/main.py"):
    # Safe to access
    pass
else:
    # Access denied
    pass
```

## Data Protection

### Secrets Management

**Never store secrets in memory files:**
```markdown
<!-- BAD: Secret in memory -->
---
id: mem_config_001
---
# API Configuration

API_KEY=sk-12345abcdef
DATABASE_PASSWORD=hunter2
```
```markdown
<!-- GOOD: Reference to environment -->
---
id: mem_config_001
---
# API Configuration

API credentials are stored in environment variables:
- `API_KEY`: API authentication key
- `DATABASE_URL`: Database connection string

Access via: `os.environ.get("API_KEY")`
```

### Environment Variables
```bash
# Store secrets in environment
export DMM_API_KEY=sk-12345abcdef
export DATABASE_URL=postgresql://user:pass@host/db

# Or use a secrets manager
export AWS_SECRET_ARN=arn:aws:secretsmanager:...
```

### File Permissions
```bash
# Secure DMM directory
chmod 700 .dmm
chmod 600 .dmm/daemon.config.json
chmod 600 .dmm/index/*.db
chmod -R 600 .dmm/memory/

# Secure system installation
chmod 700 /var/lib/dmm
chown -R dmm:dmm /var/lib/dmm
```

### Encryption at Rest

For sensitive deployments, use filesystem encryption:
```bash
# Create encrypted volume
cryptsetup luksFormat /dev/sdb1
cryptsetup open /dev/sdb1 dmm-data
mkfs.ext4 /dev/mapper/dmm-data
mount /dev/mapper/dmm-data /var/lib/dmm
```

## Agent Safety

### Self-Modification Levels

Control what agents can modify:
```json
{
  "agentos": {
    "enable_self_mod": true,
    "self_mod_approval_level": 3
  }
}
```

| Level | Changes | Approval |
|-------|---------|----------|
| 1 | Memory content updates | Automatic |
| 2 | Skill parameter changes | Logged |
| 3 | Behavior/preference changes | Human required |
| 4 | Goal/objective changes | Human required |

### Resource Quotas

Limit agent resource usage:
```python
from dmm.agentos.runtime import ResourceManager

resources = ResourceManager()

# Set quotas
resources.set_quota("agent_001", "tokens", 10000)
resources.set_quota("agent_001", "api_calls", 100)
resources.set_quota("agent_001", "file_operations", 50)

# Check before operation
if resources.check_quota("agent_001", "tokens", 500):
    # Proceed
    resources.consume("agent_001", "tokens", 500)
else:
    # Quota exceeded
    raise ResourceExhausted("Token quota exceeded")
```

### Sandboxing

For untrusted operations, use sandboxing:
```python
from dmm.agentos.runtime import Sandbox

sandbox = Sandbox(
    allowed_modules=["json", "datetime", "re"],
    denied_modules=["os", "subprocess", "socket"],
    max_execution_time=30,
    max_memory_mb=256,
)

result = sandbox.execute(code)
```

## Audit Logging

### Enable Audit Logging
```json
{
  "logging": {
    "audit": {
      "enabled": true,
      "file": "/var/log/dmm/audit.log",
      "events": [
        "memory_create",
        "memory_update",
        "memory_delete",
        "agent_action",
        "self_mod_request",
        "access_denied"
      ]
    }
  }
}
```

### Audit Log Format
```json
{
  "timestamp": "2026-01-25T12:00:00Z",
  "event": "memory_create",
  "actor": "agent_001",
  "resource": "mem_2026_01_25_001",
  "action": "create",
  "result": "success",
  "details": {
    "path": "project/new_memory.md",
    "size_bytes": 1024
  }
}
```

### Log Analysis
```bash
# Find all denied access attempts
grep '"event": "access_denied"' /var/log/dmm/audit.log | jq .

# Find self-modification requests
grep '"event": "self_mod_request"' /var/log/dmm/audit.log | jq .

# Count events by type
jq -r '.event' /var/log/dmm/audit.log | sort | uniq -c
```

## Security Checklist

### Development

- [ ] Use localhost binding
- [ ] Enable debug logging
- [ ] Review memory content before commit
- [ ] Don't commit secrets

### Staging

- [ ] Test with production-like data
- [ ] Verify path restrictions
- [ ] Test authentication
- [ ] Review audit logs

### Production

- [ ] Use HTTPS via reverse proxy
- [ ] Enable authentication
- [ ] Set restrictive file permissions
- [ ] Configure path allowlists
- [ ] Enable audit logging
- [ ] Set up log monitoring
- [ ] Configure resource quotas
- [ ] Disable unnecessary features
- [ ] Regular security updates
- [ ] Backup encryption keys

## Incident Response

### Suspected Compromise

1. **Isolate**: Stop the daemon immediately
```bash
   systemctl stop dmm
```

2. **Preserve**: Copy logs before they rotate
```bash
   cp /var/log/dmm/* /secure/incident/
```

3. **Analyze**: Review audit logs
```bash
   grep -E "access_denied|self_mod" /var/log/dmm/audit.log
```

4. **Contain**: Revoke any exposed credentials
```bash
   # Rotate API keys, passwords, etc.
```

5. **Remediate**: Fix vulnerability
6. **Document**: Record findings and actions

### Common Issues

| Issue | Indicator | Response |
|-------|-----------|----------|
| Unauthorized access | `access_denied` in logs | Review path rules |
| Resource abuse | High token/API usage | Lower quotas |
| Data exfiltration | Unusual query patterns | Review audit logs |
| Memory tampering | Unexpected changes | Restore from backup |

## Vulnerability Reporting

Report security vulnerabilities to: security@anthropic.com

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## See Also

- [Deployment Guide](deployment.md)
- [Configuration Guide](configuration.md)
- [Troubleshooting Guide](../TROUBLESHOOTING.md)
