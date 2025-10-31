# Redis Subjects Storage

Redis storage backend for KRules subjects. Provides persistent, concurrency-safe storage using Redis.

## Features

- ✅ **Persistent** - Data survives restarts
- ✅ **Concurrency-safe** - Atomic operations with WATCH/MULTI
- ✅ **Distributed** - Multiple processes/servers can share state
- ✅ **High performance** - Redis is fast and scalable

## Installation

```bash
pip install "krules-framework[redis]"
```

## Usage

### Basic Setup

```python
from dependency_injector import providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import create_redis_storage

# Create container
container = KRulesContainer()

# Create Redis storage factory
redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="myapp:"
)

# Override storage
container.subject_storage.override(providers.Object(redis_factory))

# Now subjects are persisted in Redis
user = container.subject("user-123")
user.set("email", "john@example.com")
user.store()  # Saved to Redis
```

### Configuration Options

```python
redis_factory = create_redis_storage(
    url="redis://localhost:6379/0",      # Redis URL (required)
    key_prefix="myapp:",                 # Key prefix (optional)
)
```

**URL Format:**
```
redis://[[username]:[password]]@localhost:6379/0
redis://localhost:6379/0
redis://localhost:6379
```

## Key Structure

Redis keys follow this pattern:

```
s:{key_prefix}{subject_name}
```

**Examples:**
```
s:myapp:user-123
s:myapp:device-456
s:myapp:order-789
```

Properties are stored as Redis hash fields:

```
p{property_name}  - Default property
e{property_name}  - Extended property
```

**Example hash for `user-123`:**
```redis
HGETALL s:myapp:user-123
{
    "pname": "\"John Doe\"",
    "pemail": "\"john@example.com\"",
    "page": "30",
    "elastlogin": "\"2024-01-01T12:00:00\""
}
```

## Atomic Operations

Redis storage uses `WATCH`/`MULTI` for atomic updates with lambda values:

```python
# Atomic increment - concurrency-safe
user.set("login_count", lambda c: c + 1, use_cache=False)

# Internally uses:
# WATCH s:myapp:user-123
# GET s:myapp:user-123 "plogin_count"
# MULTI
# HSET s:myapp:user-123 "plogin_count" <new_value>
# EXEC
```

## Connection Pooling

For production, configure connection pooling:

```python
import redis
from redis_subjects_storage.storage_impl import SubjectsRedisStorage

# Create connection pool
pool = redis.ConnectionPool(
    host='localhost',
    port=6379,
    db=0,
    max_connections=50,
    socket_timeout=5,
    socket_connect_timeout=5,
)

redis_client = redis.Redis(connection_pool=pool)

# Use with storage
redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="myapp:"
)
```

## Environment Variables

Configure via environment:

```python
import os
from redis_subjects_storage.storage_impl import create_redis_storage

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
key_prefix = os.getenv("REDIS_KEY_PREFIX", "app:")

redis_factory = create_redis_storage(
    url=redis_url,
    key_prefix=key_prefix
)
```

## Performance

### Batch Operations

Use caching for batch updates:

```python
# ✅ Efficient - batch operations
user = container.subject("user-123")
for i in range(100):
    user.set(f"field{i}", i)  # Cached
user.store()  # Single Redis write

# ❌ Inefficient - individual writes
for i in range(100):
    user.set(f"field{i}", i, use_cache=False)  # 100 Redis writes
```

### Hot Path Optimization

For high-frequency updates, disable cache:

```python
# Hot path - atomic write
sensor.set("last_reading", value, use_cache=False)
```

## Testing

### Test Setup

```python
import pytest
import redis
from dependency_injector import providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import create_redis_storage

@pytest.fixture
def redis_container():
    """Container with Redis storage"""
    container = KRulesContainer()

    redis_factory = create_redis_storage(
        url="redis://localhost:6379",
        key_prefix="test:"
    )
    container.subject_storage.override(providers.Object(redis_factory))

    yield container

    # Cleanup
    r = redis.Redis.from_url("redis://localhost:6379")
    for key in r.scan_iter("s:test:*"):
        r.delete(key)

@pytest.mark.asyncio
async def test_persistence(redis_container):
    user = redis_container.subject("user-123")
    user.set("email", "test@example.com")
    user.store()

    # Load in new instance
    user2 = redis_container.subject("user-123")
    assert user2.get("email") == "test@example.com"
```

## Troubleshooting

### Connection Errors

```python
# Check Redis is running
redis-cli ping  # Should return "PONG"

# Check connection from Python
import redis
r = redis.Redis.from_url("redis://localhost:6379")
r.ping()  # Should return True
```

### Key Inspection

```bash
# List all subject keys
redis-cli KEYS "s:myapp:*"

# Inspect subject
redis-cli HGETALL "s:myapp:user-123"

# Delete test keys
redis-cli DEL "s:test:user-123"
```

## See Also

- [Storage Backends](../STORAGE_BACKENDS.md) - Storage interface and patterns
- [Container & DI](../CONTAINER_DI.md) - Dependency injection
- [Advanced Patterns](../ADVANCED_PATTERNS.md) - Production patterns
