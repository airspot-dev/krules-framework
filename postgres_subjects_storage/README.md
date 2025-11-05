# PostgreSQL Subjects Storage

PostgreSQL storage backend for KRules subjects. Provides persistent, concurrency-safe storage using PostgreSQL with JSONB columns.

## Features

- ✅ **Persistent** - ACID transactions, durable storage
- ✅ **Concurrency-safe** - Row-level locks with SELECT FOR UPDATE
- ✅ **Schema-less** - JSONB columns for dynamic properties
- ✅ **SQL queries** - Full PostgreSQL query capabilities
- ✅ **Auto-schema** - Creates tables automatically on first use

## Installation

```bash
pip install "krules-framework[postgres]"
```

## Usage

### Basic Setup with Container

```python
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from postgres_subjects_storage.storage_impl import (
    create_postgres_pool,
    create_postgres_storage
)

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # PostgreSQL connection pool (Resource)
    postgres_pool = providers.Resource(
        create_postgres_pool,
        postgres_url=config.postgres.url,
        pool_min_size=config.postgres.pool_min_size,
        pool_max_size=config.postgres.pool_max_size
    )

    # KRules container
    krules = providers.Container(KRulesContainer)

    # PostgreSQL storage factory
    postgres_storage = providers.Factory(
        create_postgres_storage,
        pool=postgres_pool
    )

    # Override KRules storage
    krules.subject_storage.override(postgres_storage)

# Initialize container
container = Container()
container.config.postgres.url.from_value("postgresql://localhost:5432/krules")
container.config.postgres.pool_min_size.from_value(10)
container.config.postgres.pool_max_size.from_value(50)
container.init_resources()

# Use subjects with PostgreSQL storage
user = container.krules().subject("user-123")
user.set("email", "john@example.com")
await user.store()  # Saved to PostgreSQL
```

### Configuration with Pydantic Settings

```python
# config/settings.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class PostgresConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    url: str = "postgresql://localhost:5432/krules"
    pool_min_size: int = 10
    pool_max_size: int = 50
    command_timeout: float = 5.0

class Settings(BaseSettings):
    postgres: PostgresConfig = PostgresConfig()

# config/container.py
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from postgres_subjects_storage.storage_impl import (
    create_postgres_pool,
    create_postgres_storage
)

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    postgres_pool = providers.Resource(
        create_postgres_pool,
        postgres_url=config.postgres.url,
        pool_min_size=config.postgres.pool_min_size,
        pool_max_size=config.postgres.pool_max_size,
        command_timeout=config.postgres.command_timeout
    )

    krules = providers.Container(KRulesContainer)

    postgres_storage = providers.Factory(
        create_postgres_storage,
        pool=postgres_pool
    )

    krules.subject_storage.override(postgres_storage)

# __init__.py
from config.settings import Settings
from config.container import Container

settings = Settings()
container = Container()
container.config.from_pydantic(settings)
container.init_resources()
```

### Environment Variables

```bash
# .env
POSTGRES_URL=postgresql://user:password@localhost:5432/krules
POSTGRES_POOL_MIN_SIZE=10
POSTGRES_POOL_MAX_SIZE=50
POSTGRES_COMMAND_TIMEOUT=5.0
```

## Database Schema

The schema is created automatically on first use:

```sql
CREATE TABLE subjects (
    subject_name TEXT PRIMARY KEY,
    properties JSONB NOT NULL DEFAULT '{}',
    ext_properties JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_subjects_properties ON subjects USING GIN (properties);
CREATE INDEX idx_subjects_ext_properties ON subjects USING GIN (ext_properties);
```

### Schema Structure

**Table: `subjects`**
- `subject_name` (TEXT, PK) - Unique subject identifier
- `properties` (JSONB) - Default properties (type='p')
- `ext_properties` (JSONB) - Extended properties (type='e')
- `updated_at` (TIMESTAMP) - Last update timestamp

**Example row for `user-123`:**
```json
{
    "subject_name": "user-123",
    "properties": {
        "name": "John Doe",
        "email": "john@example.com",
        "age": 30
    },
    "ext_properties": {
        "tenant_id": "abc-123",
        "environment": "prod"
    },
    "updated_at": "2024-01-01 12:00:00"
}
```

## Atomic Operations

PostgreSQL storage uses `SELECT FOR UPDATE` for atomic updates with callable values:

```python
# Atomic increment - concurrency-safe
await user.set("login_count", lambda c: c + 1, use_cache=False)

# Internally uses:
# BEGIN TRANSACTION
# SELECT properties FROM subjects WHERE subject_name = 'user-123' FOR UPDATE
# -- Compute new value from lambda
# UPDATE subjects SET properties = properties || '{"login_count": <new>}'
# COMMIT
```

### Concurrency Safety

- **Row-level locks**: Serialize access to same subject
- **ACID transactions**: Guaranteed atomicity
- **Pessimistic locking**: SELECT FOR UPDATE prevents race conditions

## Performance

### Batch Operations

Use caching for batch updates:

```python
# ✅ Efficient - batch operations
user = container.krules().subject("user-123")
for i in range(100):
    user.set(f"field{i}", i)  # Cached
await user.store()  # Single PostgreSQL write

# ❌ Inefficient - individual writes
for i in range(100):
    await user.set(f"field{i}", i, use_cache=False)  # 100 PostgreSQL writes
```

### Connection Pooling

Connection pool is managed automatically:

```python
pool = await create_postgres_pool(
    postgres_url="postgresql://localhost:5432/krules",
    pool_min_size=10,    # Min connections
    pool_max_size=50,    # Max connections
    command_timeout=5.0  # Timeout in seconds
)
```

**Pool sizing guidelines:**
- `pool_min_size`: ~10 per worker process
- `pool_max_size`: ~50 per worker process
- `command_timeout`: 5-10 seconds for most workloads

### Query Performance

JSONB columns have GIN indexes for efficient queries:

```sql
-- Find subjects with specific property value
SELECT subject_name
FROM subjects
WHERE properties @> '{"status": "active"}';

-- Query extended properties
SELECT subject_name
FROM subjects
WHERE ext_properties ? 'tenant_id';
```

## Testing

### Test Setup

```python
import pytest
import pytest_asyncio
import asyncpg
from dependency_injector import providers
from krules_core.container import KRulesContainer
from postgres_subjects_storage.storage_impl import (
    create_postgres_pool,
    create_postgres_storage
)

@pytest_asyncio.fixture(scope="session")
async def postgres_pool():
    """PostgreSQL pool for testing"""
    pool = await asyncpg.create_pool(
        dsn="postgresql://localhost:5432/krules_test",
        min_size=2,
        max_size=10
    )
    yield pool
    await pool.close()

@pytest_asyncio.fixture(autouse=True)
async def cleanup_postgres(postgres_pool):
    """Clean database before/after each test"""
    async with postgres_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS subjects CASCADE")
    yield
    async with postgres_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS subjects CASCADE")

@pytest_asyncio.fixture
async def postgres_container(postgres_pool):
    """Container with PostgreSQL storage"""
    container = KRulesContainer()

    postgres_factory = create_postgres_storage(pool=postgres_pool)
    container.subject_storage.override(providers.Object(postgres_factory))

    return container

@pytest.mark.asyncio
async def test_persistence(postgres_container):
    user = postgres_container.subject("user-123")
    user.set("email", "test@example.com")
    await user.store()

    # Load in new instance
    user2 = postgres_container.subject("user-123")
    assert user2.get("email") == "test@example.com"
```

## Troubleshooting

### Connection Errors

```bash
# Check PostgreSQL is running
psql -h localhost -U postgres -c "SELECT 1"

# Test connection from Python
import asyncpg
pool = await asyncpg.create_pool("postgresql://localhost:5432/krules")
async with pool.acquire() as conn:
    result = await conn.fetchval("SELECT 1")
    print(result)  # Should print: 1
```

### Database Inspection

```sql
-- List all subjects
SELECT subject_name, properties, ext_properties
FROM subjects;

-- Inspect specific subject
SELECT * FROM subjects WHERE subject_name = 'user-123';

-- Query by property value
SELECT subject_name, properties->>'name' AS name
FROM subjects
WHERE properties @> '{"status": "active"}';

-- Delete test subjects
DELETE FROM subjects WHERE subject_name LIKE 'test-%';
```

### Schema Management

The schema is created automatically, but you can also create it manually:

```bash
# Create schema from SQL
psql $DATABASE_URL -c "
CREATE TABLE IF NOT EXISTS subjects (
    subject_name TEXT PRIMARY KEY,
    properties JSONB NOT NULL DEFAULT '{}',
    ext_properties JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subjects_properties
ON subjects USING GIN (properties);

CREATE INDEX IF NOT EXISTS idx_subjects_ext_properties
ON subjects USING GIN (ext_properties);
"
```

## Migration from Redis

If you're migrating from Redis storage:

1. **Data structure is compatible** - Both use JSON serialization
2. **API is identical** - Same storage interface
3. **Migration script example:**

```python
import asyncio
import json
import asyncpg
import redis

async def migrate_redis_to_postgres():
    # Connect to Redis
    r = redis.Redis.from_url("redis://localhost:6379")

    # Connect to PostgreSQL
    conn = await asyncpg.connect("postgresql://localhost:5432/krules")

    # Migrate each subject
    for key in r.scan_iter("s:myapp:*"):
        # Extract subject name
        subject_name = key.decode().replace("s:myapp:", "")

        # Load Redis hash
        hash_data = r.hgetall(key)

        # Parse properties
        properties = {}
        ext_properties = {}

        for field, value in hash_data.items():
            field = field.decode()
            value = json.loads(value)

            if field.startswith('p'):
                properties[field[1:]] = value
            elif field.startswith('e'):
                ext_properties[field[1:]] = value

        # Insert into PostgreSQL
        await conn.execute("""
            INSERT INTO subjects (subject_name, properties, ext_properties)
            VALUES ($1, $2, $3)
            ON CONFLICT (subject_name) DO UPDATE SET
                properties = EXCLUDED.properties,
                ext_properties = EXCLUDED.ext_properties
        """, subject_name, json.dumps(properties), json.dumps(ext_properties))

        print(f"Migrated {subject_name}")

    await conn.close()

# Run migration
asyncio.run(migrate_redis_to_postgres())
```

## Comparison: PostgreSQL vs Redis

| Feature | PostgreSQL | Redis |
|---------|------------|-------|
| **Persistence** | ACID, durable | RDB/AOF snapshots |
| **Concurrency** | SELECT FOR UPDATE | WATCH/MULTI/EXEC |
| **Query capabilities** | Full SQL + JSONB | Limited (SCAN, keys) |
| **Transactions** | Multi-row ACID | Single-key atomic |
| **Performance** | 10-50k ops/sec | 100k+ ops/sec |
| **Storage** | On-disk, compressed | In-memory + disk |
| **Best for** | Complex queries, durability | High throughput, simplicity |

## See Also

- [Storage Backends](../STORAGE_BACKENDS.md) - Storage interface and patterns
- [Container & DI](../CONTAINER_DI.md) - Dependency injection
- [Advanced Patterns](../ADVANCED_PATTERNS.md) - Production patterns
