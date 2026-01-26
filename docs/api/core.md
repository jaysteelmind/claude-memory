# Core API Reference

The core module provides fundamental types, constants, and exceptions used throughout DMM.

## Module: dmm.core.constants

### Scope

Memory scope categories with semantic meaning.
```python
from dmm.core.constants import Scope

class Scope(str, Enum):
    BASELINE = "baseline"   # Critical, always-loaded context
    GLOBAL = "global"       # Cross-project knowledge
    AGENT = "agent"         # Agent behavior rules
    PROJECT = "project"     # Project-specific memories
    EPHEMERAL = "ephemeral" # Temporary findings
```

**Usage:**
```python
from dmm.core.constants import Scope

memory.scope = Scope.PROJECT
if memory.scope == Scope.BASELINE:
    # Always include this memory
    pass
```

### Confidence

Memory maturity levels.
```python
class Confidence(str, Enum):
    EXPERIMENTAL = "experimental"  # New, untested
    ACTIVE = "active"              # In regular use
    STABLE = "stable"              # Well-established
    DEPRECATED = "deprecated"      # Scheduled for removal
```

### Status

Memory lifecycle status.
```python
class Status(str, Enum):
    ACTIVE = "active"         # Available for retrieval
    DEPRECATED = "deprecated" # Excluded from retrieval
```

### Key Constants
```python
# Embedding configuration
EMBEDDING_DIMENSION = 384
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Token budgets
DEFAULT_TOTAL_BUDGET = 2000
DEFAULT_BASELINE_BUDGET = 800
MIN_MEMORY_TOKENS = 300
MAX_MEMORY_TOKENS = 800

# Retrieval weights
SIMILARITY_WEIGHT = 0.6
PRIORITY_WEIGHT = 0.25
CONFIDENCE_WEIGHT = 0.15

# Network
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7433
```

## Module: dmm.core.exceptions

### Base Exceptions
```python
class DMMError(Exception):
    """Base exception for all DMM errors."""
    pass
```

### Specific Exceptions
```python
class ConfigError(DMMError):
    """Configuration-related errors."""
    pass

class IndexError(DMMError):
    """Indexing-related errors."""
    pass

class StoreError(DMMError):
    """Storage-related errors."""
    
    def __init__(
        self,
        message: str,
        memory_id: str | None = None,
        operation: str | None = None,
    ):
        self.memory_id = memory_id
        self.operation = operation
        super().__init__(message)

class RetrievalError(DMMError):
    """Retrieval-related errors."""
    pass

class ValidationError(DMMError):
    """Validation-related errors."""
    pass

class ConflictError(DMMError):
    """Conflict detection errors."""
    pass

class ReviewError(DMMError):
    """Review process errors."""
    pass
```

**Usage:**
```python
from dmm.core.exceptions import StoreError, ValidationError

try:
    store.upsert_memory(memory, embedding)
except StoreError as e:
    print(f"Failed to store {e.memory_id}: {e}")
except ValidationError as e:
    print(f"Invalid memory: {e}")
```

## Module: dmm.models.memory

### MemoryFile

Represents a parsed memory markdown file.
```python
from dataclasses import dataclass
from datetime import datetime
from dmm.core.constants import Scope, Confidence, Status

@dataclass
class MemoryFile:
    # Identity
    id: str              # Unique identifier (mem_YYYY_MM_DD_NNN)
    path: str            # File path relative to memory root
    
    # Content
    title: str           # H1 heading from content
    body: str            # Full markdown body
    token_count: int     # Estimated token count
    
    # Metadata
    tags: list[str]      # Semantic tags (1-10)
    scope: Scope         # Memory scope
    priority: float      # 0.0-1.0 retrieval priority
    confidence: Confidence
    status: Status
    
    # Optional
    created: datetime | None = None
    last_used: datetime | None = None
    usage_count: int = 0
    supersedes: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    expires: datetime | None = None
    
    # Derived
    directory: str       # Computed from path
```

**Methods:**
```python
def to_dict(self) -> dict[str, Any]:
    """Convert to dictionary for serialization."""

def __post_init__(self) -> None:
    """Compute derived fields after initialization."""
```

**Usage:**
```python
from dmm.models.memory import MemoryFile
from dmm.core.constants import Scope, Confidence, Status

memory = MemoryFile(
    id="mem_2026_01_25_001",
    path="project/error_handling.md",
    title="Error Handling Guidelines",
    body="Always use specific exception types...",
    token_count=150,
    tags=["errors", "exceptions"],
    scope=Scope.PROJECT,
    priority=0.7,
    confidence=Confidence.ACTIVE,
    status=Status.ACTIVE,
)

# Convert to dict
data = memory.to_dict()
```

### IndexedMemory

Represents a memory stored in the vector database.
```python
@dataclass
class IndexedMemory:
    id: str
    path: str
    directory: str
    title: str
    body: str
    scope: str
    priority: float
    confidence: str
    status: str
    tags: list[str]
    token_count: int
    file_hash: str
    indexed_at: datetime
```

### DirectoryInfo

Information about a memory directory.
```python
@dataclass
class DirectoryInfo:
    path: str
    file_count: int
    avg_priority: float
    scopes: list[str]
    last_updated: datetime
```

## Module: dmm.models.pack

### MemoryEntry

A single entry in a memory pack.
```python
@dataclass
class MemoryEntry:
    memory_id: str
    path: str
    title: str
    content: str
    token_count: int
    relevance_score: float
    source: str  # "baseline", "retrieved", "graph"
```

### MemoryPack

Assembled context for a query.
```python
@dataclass
class MemoryPack:
    query: str
    entries: list[MemoryEntry]
    total_tokens: int
    budget: int
    baseline_tokens: int
    retrieved_tokens: int
    timestamp: datetime
    
    def to_markdown(self) -> str:
        """Format pack as markdown for context injection."""
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
```

**Usage:**
```python
from dmm.models.pack import MemoryPack

pack = retriever.retrieve("error handling", budget=2000)

# Use as context
context = pack.to_markdown()

# Inspect entries
for entry in pack.entries:
    print(f"{entry.title}: {entry.relevance_score:.2f}")
```

## Module: dmm.models.query

### SearchFilters

Filters for memory search.
```python
@dataclass
class SearchFilters:
    scopes: list[Scope] | None = None
    tags: list[str] | None = None
    min_priority: float | None = None
    min_confidence: Confidence | None = None
    exclude_deprecated: bool = True
    exclude_ephemeral: bool = False
```

### QueryResult

Result of a memory query.
```python
@dataclass
class QueryResult:
    memory: IndexedMemory
    similarity_score: float
    final_score: float
    matched_tags: list[str]
```

## See Also

- [Graph API](graph.md) - Knowledge graph operations
- [AgentOS API](agentos/index.md) - Agent Operating System
- [Memory Format](../MEMORY_FORMAT.md) - File format specification
