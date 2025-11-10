# Storage Backends

KRules supports pluggable storage backends for persisting subject state. Choose between in-memory, Redis, or implement custom storage.

## Storage Interface

All storage backends implement a common interface:

```python
class SubjectStorage:
    def __init__(self, subject_name, event_info=None, event_data=None):
        """Initialize storage for a subject"""
        pass

    async def load(self) -> tuple[dict, dict]:
        """Load subject state
        Returns: (properties_dict, ext_properties_dict)
        """
        pass

    async def store(self, inserts=[], updates=[], deletes=[]):
        """Persist property changes in batch"""
        pass

    async def set(self, prop) -> tuple[Any, Any]:
        """Set single property atomically
        Returns: (new_value, old_value)
        """
        pass

    async def get(self, prop) -> Any:
        """Get property value"""
        pass

    async def delete(self, prop):
        """Delete property"""
        pass

    async def flush(self):
        """Delete entire subject from storage"""
        pass

    async def get_ext_props(self) -> dict:
        """Get all extended properties"""
        pass

    def is_concurrency_safe(self) -> bool:
        """Whether storage supports concurrent access"""
        return False

    def is_persistent(self) -> bool:
        """Whether storage persists across restarts"""
        return False
```

## Built-in Backends

### EmptySubjectStorage (In-Memory)

**Default storage** - Non-persistent, in-memory only.

**Characteristics:**
- ✅ Fast (no I/O)
- ✅ Simple setup
- ❌ Non-persistent (lost on restart)
- ❌ Not concurrency-safe
- ✅ Good for development and testing

**Usage:**

```python
from krules_core.container import KRulesContainer

# Default - uses EmptySubjectStorage
container = KRulesContainer()
user = container.subject("user-123")
await user.set("email", "john@example.com")
# Data only exists in memory
```

**When to use:**
- Development
- Testing
- Ephemeral data
- Proof of concepts

### SubjectsRedisStorage (Redis)

**Production storage** - Persistent, concurrency-safe.

**Characteristics:**
- ✅ Persistent across restarts
- ✅ Concurrency-safe (atomic operations)
- ✅ Distributed (multi-process/multi-server)
- ✅ High performance
- ⚠️ Requires Redis server

**Installation:**

```bash
pip install "krules-framework[redis]"
```

**Usage:**

```python
from dependency_injector import providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import create_redis_storage

# Create container
container = KRulesContainer()

# Create Redis storage factory (uses redis.asyncio)
redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="myapp:"
)

# Override storage
container.subject_storage.override(providers.Object(redis_factory))

# Now all subjects use Redis (fully async)
user = container.subject("user-123")
await user.set("email", "john@example.com")
await user.store()  # Persisted in Redis
```

**Configuration Options:**

```python
redis_factory = create_redis_storage(
    url="redis://localhost:6379/0",      # Redis URL (required)
    key_prefix="myapp:",                 # Key prefix (optional)
    # Additional redis.Redis() options:
    # decode_responses=False,
    # max_connections=50,
    # socket_timeout=5,
    # etc.
)
```

**Key Structure:**

Redis keys follow this pattern:
```
s:{key_prefix}{subject_name}
```

Example:
```
s:myapp:user-123
s:myapp:device-456
s:myapp:order-789
```

Properties stored as hash fields:
```
p{property_name}  - Default property
e{property_name}  - Extended property
```

Example hash for `user-123`:
```
HGETALL s:myapp:user-123
{
    "pname": "\"John Doe\"",
    "pemail": "\"john@example.com\"",
    "page": "30",
    "elastlogin": "\"2024-01-01T12:00:00\""
}
```

**Atomic Operations:**

Redis storage uses `WATCH`/`MULTI` for atomic updates with lambda values:

```python
# Atomic increment
await user.set("login_count", lambda c: c + 1, use_cache=False)

# Internally uses Redis WATCH to ensure atomicity
```

**When to use:**
- Production environments
- Multiple workers/processes
- Distributed systems
- Data must persist across restarts

## Implementing Custom Storage

Create custom storage by implementing the interface:

### Example: SQLite Storage

```python
import sqlite3
import json

class SQLiteSubjectStorage:
    def __init__(self, subject_name, db_path="subjects.db", event_info=None, event_data=None):
        self._subject = subject_name
        self._db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS subjects (
                subject TEXT,
                property TEXT,
                value TEXT,
                is_extended INTEGER,
                PRIMARY KEY (subject, property, is_extended)
            )
        """)
        conn.commit()
        conn.close()

    def load(self):
        """Load subject properties"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.execute(
            "SELECT property, value, is_extended FROM subjects WHERE subject = ?",
            (self._subject,)
        )

        props = {}
        ext_props = {}

        for row in cursor:
            prop_name, value, is_extended = row
            value = json.loads(value)

            if is_extended:
                ext_props[prop_name] = value
            else:
                props[prop_name] = value

        conn.close()
        return props, ext_props

    def store(self, inserts=[], updates=[], deletes=[]):
        """Persist changes"""
        conn = sqlite3.connect(self._db_path)

        # Insert/Update
        for prop in inserts + updates:
            is_extended = 1 if prop.type == 'e' else 0
            conn.execute(
                """
                INSERT OR REPLACE INTO subjects (subject, property, value, is_extended)
                VALUES (?, ?, ?, ?)
                """,
                (self._subject, prop.name, prop.json_value(), is_extended)
            )

        # Delete
        for prop in deletes:
            is_extended = 1 if prop.type == 'e' else 0
            conn.execute(
                "DELETE FROM subjects WHERE subject = ? AND property = ? AND is_extended = ?",
                (self._subject, prop.name, is_extended)
            )

        conn.commit()
        conn.close()

    def set(self, prop):
        """Set single property"""
        # Get old value
        conn = sqlite3.connect(self._db_path)
        is_extended = 1 if prop.type == 'e' else 0
        cursor = conn.execute(
            "SELECT value FROM subjects WHERE subject = ? AND property = ? AND is_extended = ?",
            (self._subject, prop.name, is_extended)
        )
        row = cursor.fetchone()
        old_value = json.loads(row[0]) if row else None

        # Compute new value (handle lambdas)
        new_value = prop.get_value(old_value)

        # Store
        conn.execute(
            """
            INSERT OR REPLACE INTO subjects (subject, property, value, is_extended)
            VALUES (?, ?, ?, ?)
            """,
            (self._subject, prop.name, json.dumps(new_value), is_extended)
        )
        conn.commit()
        conn.close()

        return new_value, old_value

    def get(self, prop):
        """Get property value"""
        conn = sqlite3.connect(self._db_path)
        is_extended = 1 if prop.type == 'e' else 0
        cursor = conn.execute(
            "SELECT value FROM subjects WHERE subject = ? AND property = ? AND is_extended = ?",
            (self._subject, prop.name, is_extended)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise AttributeError(f"Property {prop.name} not found")

        return json.loads(row[0])

    def delete(self, prop):
        """Delete property"""
        conn = sqlite3.connect(self._db_path)
        is_extended = 1 if prop.type == 'e' else 0
        conn.execute(
            "DELETE FROM subjects WHERE subject = ? AND property = ? AND is_extended = ?",
            (self._subject, prop.name, is_extended)
        )
        conn.commit()
        conn.close()

    def flush(self):
        """Delete entire subject"""
        conn = sqlite3.connect(self._db_path)
        conn.execute("DELETE FROM subjects WHERE subject = ?", (self._subject,))
        conn.commit()
        conn.close()

    def get_ext_props(self):
        """Get extended properties"""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.execute(
            "SELECT property, value FROM subjects WHERE subject = ? AND is_extended = 1",
            (self._subject,)
        )
        ext_props = {row[0]: json.loads(row[1]) for row in cursor}
        conn.close()
        return ext_props

    def is_concurrency_safe(self):
        return False  # SQLite with file locking

    def is_persistent(self):
        return True
```

### Use Custom Storage

```python
from dependency_injector import providers
from krules_core.container import KRulesContainer

def create_sqlite_storage(db_path="subjects.db"):
    """Factory function for SQLite storage"""
    def factory(name, event_info=None, event_data=None):
        return SQLiteSubjectStorage(name, db_path, event_info, event_data)
    return factory

# Create container
container = KRulesContainer()

# Override with SQLite storage
sqlite_factory = create_sqlite_storage("myapp.db")
container.subject_storage.override(providers.Object(sqlite_factory))

# Use subjects
user = container.subject("user-123")
await user.set("email", "john@example.com")
await user.store()  # Persisted in SQLite
```

## Storage Patterns

### Factory Pattern

```python
def create_storage_factory(storage_type, **config):
    """Create storage factory based on type"""
    if storage_type == "redis":
        return create_redis_storage(
            url=config.get("url", "redis://localhost:6379"),
            key_prefix=config.get("key_prefix", "")
        )
    elif storage_type == "sqlite":
        return create_sqlite_storage(
            db_path=config.get("db_path", "subjects.db")
        )
    else:
        # Default in-memory
        return create_empty_storage()

# Use factory
storage_factory = create_storage_factory(
    storage_type="redis",
    url="redis://localhost:6379",
    key_prefix="myapp:"
)

container = KRulesContainer()
container.subject_storage.override(providers.Object(storage_factory))
```

### Multi-Backend Pattern

Use different storage for different subjects:

```python
def create_hybrid_storage(default_storage, special_storage, special_prefix):
    """Route subjects to different storage backends"""
    def factory(name, event_info=None, event_data=None):
        if name.startswith(special_prefix):
            return special_storage(name, event_info, event_data)
        else:
            return default_storage(name, event_info, event_data)
    return factory

# Route "cache-*" subjects to in-memory, others to Redis
redis_storage = create_redis_storage("redis://localhost:6379", "app:")
memory_storage = create_empty_storage()

hybrid_factory = create_hybrid_storage(
    default_storage=redis_storage,
    special_storage=memory_storage,
    special_prefix="cache-"
)

container = KRulesContainer()
container.subject_storage.override(providers.Object(hybrid_factory))

# Uses Redis
user = container.subject("user-123")

# Uses in-memory
cache = container.subject("cache-temp-data")
```

## Performance Considerations

### Caching vs Direct

```python
# ✅ Batch operations - use cache
await user.set("field1", "value1")
await user.set("field2", "value2")
await user.set("field3", "value3")
await user.store()  # Single write to storage

# ✅ Hot path - disable cache
await user.set("counter", lambda c: c + 1, use_cache=False)  # Direct atomic write

# ❌ Inefficient - store after each change
await user.set("field1", "value1")
await user.store()
await user.set("field2", "value2")
await user.store()
```

### Connection Pooling

For Redis (async):

```python
from redis.asyncio import Redis, ConnectionPool

# Async connection pool
pool = ConnectionPool(
    host='localhost',
    port=6379,
    db=0,
    max_connections=50
)

redis_client = Redis(connection_pool=pool)

# Use with storage (uses async Redis client)
redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="app:"
)
```

## Best Practices

1. **Choose storage based on requirements**:
   - Development: `EmptySubjectStorage`
   - Production: `SubjectsRedisStorage`
   - Custom needs: Implement custom storage

2. **Key prefixes** - Use prefixes to namespace data:
   ```python
   create_redis_storage(url="redis://...", key_prefix="myapp:")
   ```

3. **Batch writes** - Use caching for batch operations:
   ```python
   for i in range(100):
       await subject.set(f"field{i}", i)
   await subject.store()  # Single write
   ```

4. **Atomic operations** - Use `use_cache=False` for atomicity:
   ```python
   await subject.set("counter", lambda c: c + 1, use_cache=False)
   ```

5. **Test with real storage** - Test with production storage backend in integration tests

6. **Monitor performance** - Track storage operation times and optimize

## Testing Storage Backends

```python
import pytest

@pytest.mark.asyncio
async def test_storage_interface():
    """Test custom storage implementation"""
    storage = MySQLiteStorage("test-subject")

    # Test load (should be empty)
    props, ext_props = await storage.load()
    assert props == {}
    assert ext_props == {}

    # Test set
    from krules_core.subject import SubjectProperty
    prop = SubjectProperty("email", "test@example.com")
    new_val, old_val = await storage.set(prop)
    assert new_val == "test@example.com"
    assert old_val is None

    # Test get
    value = await storage.get(prop)
    assert value == "test@example.com"

    # Test delete
    await storage.delete(prop)
    with pytest.raises(AttributeError):
        await storage.get(prop)

    # Test flush
    await storage.set(SubjectProperty("name", "John"))
    await storage.flush()
    props, ext_props = await storage.load()
    assert props == {}
```

## What's Next?

- [Container & DI](CONTAINER_DI.md) - Dependency injection
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [Testing](TESTING.md) - Testing strategies
- [API Reference](API_REFERENCE.md) - Complete API
