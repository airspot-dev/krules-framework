# Redis Subjects Storage

Async Redis storage backend for KRules subjects. Provides persistent, concurrency-safe storage using Redis with full async/await support.

## Features

- ✅ **Fully async** - Uses redis.asyncio for non-blocking I/O
- ✅ **Persistent** - Data survives restarts
- ✅ **Concurrency-safe** - Atomic operations with WATCH/MULTI/EXEC
- ✅ **Distributed** - Multiple processes/servers can share state
- ✅ **High performance** - Redis is fast and scalable

## Installation

```bash
pip install "krules-framework[redis]"
```

## Usage

### Basic Setup with Container

```python
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import (
    create_redis_client,
    create_redis_storage
)

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Redis client (Resource)
    redis_client = providers.Resource(
        create_redis_client,
        redis_url=config.redis.url
    )

    # KRules container
    krules = providers.Container(KRulesContainer)

    # Redis storage factory
    redis_storage = providers.Factory(
        create_redis_storage,
        redis_client=redis_client,
        redis_prefix=config.redis.key_prefix
    )

    # Override KRules storage
    krules.subject_storage.override(redis_storage)

# Initialize container
container = Container()
container.config.redis.url.from_value("redis://localhost:6379/0")
container.config.redis.key_prefix.from_value("myapp:")
container.init_resources()

# Use subjects with Redis storage (requires async Subject - PHASE 1 Task 1)
# user = container.krules().subject("user-123")
# user.name = "John"
# await user.store()  # Saved to Redis
```

### Configuration Options

```python
# Create async Redis client
client = await create_redis_client(
    redis_url="redis://localhost:6379/0"  # Redis URL (required)
)

# Create storage factory
redis_factory = create_redis_storage(
    redis_client=client,              # Async Redis client (required)
    redis_prefix="myapp:"              # Key prefix (optional)
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

Redis storage uses async `WATCH`/`MULTI`/`EXEC` for atomic updates with callable values:

```python
# Atomic increment - concurrency-safe (requires async Subject)
# await user.set("login_count", lambda c: c + 1, use_cache=False)

# Internally uses (async):
# async with pipeline:
#     await pipeline.watch(skey)
#     old_value = await pipeline.hget(skey, pname)
#     pipeline.multi()
#     new_value = callable(old_value)
#     pipeline.hset(skey, pname, new_value)
#     await pipeline.execute()
```

### Concurrency Safety

- **Optimistic locking**: WATCH/MULTI/EXEC prevents race conditions
- **Retry loop**: Automatic retry on WatchError
- **Atomic read-modify-write**: Callable values are applied atomically

## Connection Management

Redis async client handles connection pooling automatically:

```python
from redis.asyncio import Redis
from redis_subjects_storage.storage_impl import create_redis_client

# Simple client (automatic connection pool)
client = await create_redis_client("redis://localhost:6379/0")

# With custom options
from redis.asyncio import Redis

client = Redis.from_url(
    "redis://localhost:6379/0",
    decode_responses=False,
    max_connections=50,
    socket_connect_timeout=5.0,
    socket_timeout=5.0,
    health_check_interval=30
)

# Use with storage factory
redis_factory = create_redis_storage(
    redis_client=client,
    redis_prefix="myapp:"
)
```

## Environment Variables

Configure via environment (using pydantic-settings):

```python
# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = "redis://localhost:6379/0"
    key_prefix: str = "app:"

class Settings(BaseSettings):
    redis: RedisConfig = RedisConfig()

# config/container.py
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import (
    create_redis_client,
    create_redis_storage
)

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    redis_client = providers.Resource(
        create_redis_client,
        redis_url=config.redis.url
    )

    krules = providers.Container(KRulesContainer)

    redis_storage = providers.Factory(
        create_redis_storage,
        redis_client=redis_client,
        redis_prefix=config.redis.key_prefix
    )

    krules.subject_storage.override(redis_storage)

# __init__.py
from config.settings import Settings
from config.container import Container

settings = Settings()
container = Container()
container.config.from_pydantic(settings)
container.init_resources()
```

**Environment variables:**
```bash
# .env
REDIS_URL=redis://user:password@localhost:6379/0
REDIS_KEY_PREFIX=myapp:
```

## Performance

### Batch Operations

Use caching for batch updates (requires async Subject):

```python
# ✅ Efficient - batch operations
# user = container.subject("user-123")
# for i in range(100):
#     user.set(f"field{i}", i)  # Cached
# await user.store()  # Single Redis write

# ❌ Inefficient - individual writes
# for i in range(100):
#     await user.set(f"field{i}", i, use_cache=False)  # 100 Redis writes
```

### Async Performance Benefits

- **Non-blocking I/O**: Multiple async operations can run concurrently
- **Connection efficiency**: Automatic connection pooling
- **Better throughput**: 100k+ ops/sec possible with async

## Testing

### Test Setup with pytest-asyncio

```python
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from redis_subjects_storage.storage_impl import SubjectsRedisStorage

@pytest_asyncio.fixture
async def redis_client():
    """Create async Redis client for testing."""
    client = Redis.from_url("redis://localhost:6379/0", decode_responses=False)

    # Verify connection
    try:
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not available: {e}")

    yield client

    # Cleanup: close connection
    await client.aclose()

@pytest_asyncio.fixture(autouse=True)
async def cleanup_redis(redis_client):
    """Clean up test keys before and after each test."""
    # Pre-cleanup
    keys = []
    async for key in redis_client.scan_iter("s:test:*"):
        keys.append(key)
    if keys:
        await redis_client.delete(*keys)

    yield

    # Post-cleanup
    keys = []
    async for key in redis_client.scan_iter("s:test:*"):
        keys.append(key)
    if keys:
        await redis_client.delete(*keys)

@pytest_asyncio.fixture
async def redis_storage(redis_client):
    """Create SubjectsRedisStorage instance for testing."""
    return SubjectsRedisStorage(
        subject="test-subject",
        redis_client=redis_client,
        key_prefix="test:"
    )

@pytest.mark.asyncio
async def test_redis_storage(redis_storage):
    """Test async Redis storage operations."""
    from krules_core.subject import PropertyType
    import json

    class Property:
        def __init__(self, name, value, prop_type=PropertyType.DEFAULT):
            self.name = name
            self.value = value
            self.type = prop_type

        def json_value(self, old_value=None):
            if callable(self.value):
                result = self.value(old_value)
                return json.dumps(result)
            return json.dumps(self.value)

    # Test store and load
    prop = Property("email", "test@example.com")
    await redis_storage.store(inserts=[prop])

    default_props, _ = await redis_storage.load()
    assert default_props["email"] == "test@example.com"
```

## Troubleshooting

### Connection Errors

```bash
# Check Redis is running
redis-cli ping  # Should return "PONG"
```

```python
# Check async connection from Python
from redis.asyncio import Redis

async def test_connection():
    client = Redis.from_url("redis://localhost:6379/0")
    try:
        result = await client.ping()
        print(f"Connection OK: {result}")  # Should print: True
    finally:
        await client.aclose()

# Run async test
import asyncio
asyncio.run(test_connection())
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
