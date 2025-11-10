# Container & Dependency Injection

KRules uses dependency injection to manage components and their dependencies. The `KRulesContainer` provides a clean, testable architecture.

## Why Dependency Injection?

**Benefits:**
- **Testability** - Easy to mock dependencies in tests
- **Flexibility** - Swap implementations (storage backends, event bus)
- **Separation of Concerns** - Components don't manage their own dependencies
- **Configuration** - Centralized setup

## KRulesContainer

The container manages all framework components:

```python
from krules_core.container import KRulesContainer

# Create container
container = KRulesContainer()

# Get handlers (decorators and emit function)
on, when, middleware, emit = container.handlers()

# Create subjects
user = container.subject("user-123")
```

## Container Providers

The container defines four providers:

### 1. event_bus (Singleton)

**Type:** Singleton
**Purpose:** Central event routing

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()

# Access event bus (rarely needed directly)
event_bus = container.event_bus()
```

The event bus is automatically injected into handlers via `.handlers()`.

### 2. subject_storage (Callable Factory)

**Type:** Callable
**Purpose:** Creates storage instances for subjects

**Default:** `EmptySubjectStorage` (in-memory, non-persistent)

```python
# Default usage (in-memory storage)
container = KRulesContainer()
user = container.subject("user-123")  # Uses EmptySubjectStorage
```

### 3. subject (Factory)

**Type:** Factory
**Purpose:** Creates `Subject` instances

```python
# Create subjects
user = container.subject("user-123")
device = container.subject("device-456")

# Subjects are created with injected storage and event_bus
```

### 4. handlers (Callable)

**Type:** Callable
**Purpose:** Returns handler decorators and emit function

```python
# Get handlers bound to this container's event bus
on, when, middleware, emit = container.handlers()

# Now decorators are bound to container's event bus
@on("user.action")
async def handler(ctx):
    pass
```

## Using the Container

### Basic Usage

```python
from krules_core.container import KRulesContainer

# 1. Create container
container = KRulesContainer()

# 2. Get handlers
on, when, middleware, emit = container.handlers()

# 3. Define handlers
@on("user.login")
async def handle_login(ctx):
    await ctx.subject.set("last_login", datetime.now())

# 4. Create subjects
user = container.subject("user-123")
await user.set("email", "john@example.com")

# 5. Emit events
await emit("user.login", user)
```

### Typical Application Structure

```python
# app.py
from krules_core.container import KRulesContainer

# Initialize container
container = KRulesContainer()

# Configure storage (if needed)
# ... override providers here ...

# Get handlers
on, when, middleware, emit = container.handlers()

# Import handlers modules (they use the decorators above)
from . import user_handlers
from . import order_handlers
from . import device_handlers

# Application logic
async def main():
    # Use container to create subjects and emit events
    user = container.subject("user-123")
    await emit("app.started", user)
```

## Overriding Providers

Customize the container by overriding providers.

### Override Storage Backend

Use Redis instead of in-memory storage:

```python
from dependency_injector import providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import create_redis_storage

# Create container
container = KRulesContainer()

# Create Redis storage factory
from redis.asyncio import Redis
redis_client = await create_redis_client("redis://localhost:6379")
redis_factory = create_redis_storage(
    redis_client=redis_client,
    redis_prefix="myapp:"
)

# Override storage provider
container.subject_storage.override(providers.Object(redis_factory))

# Now all subjects use Redis
user = container.subject("user-123")
await user.set("email", "john@example.com")
await user.store()  # Persists to Redis
```

### Custom Storage Backend

Implement and inject custom storage:

```python
from dependency_injector import providers

# Define custom storage factory
def create_custom_storage():
    def factory(name, event_info=None, event_data=None):
        return MyCustomStorage(name)
    return factory

container = KRulesContainer()
custom_factory = create_custom_storage()
container.subject_storage.override(providers.Object(custom_factory))
```

### Override Event Bus

Replace the event bus (advanced use case):

```python
from krules_core.event_bus import EventBus

class CustomEventBus(EventBus):
    """Custom event bus with additional features"""

    async def emit(self, event_type, subject, payload, **extra):
        # Custom logic before emission
        print(f"Custom emit: {event_type}")
        await super().emit(event_type, subject, payload, **extra)

container = KRulesContainer()
container.event_bus.override(providers.Singleton(CustomEventBus))

# Handlers now use CustomEventBus
on, when, middleware, emit = container.handlers()
```

## Multiple Containers

Use multiple containers for isolation:

```python
# Container for tenant A
container_a = KRulesContainer()
redis_client_a = await create_redis_client("redis://localhost:6379")
redis_a = create_redis_storage(redis_client_a, "tenant_a:")
container_a.subject_storage.override(providers.Object(redis_a))

# Container for tenant B
container_b = KRulesContainer()
redis_client_b = await create_redis_client("redis://localhost:6379")
redis_b = create_redis_storage(redis_client_b, "tenant_b:")
container_b.subject_storage.override(providers.Object(redis_b))

# Each container has isolated event bus and storage
user_a = container_a.subject("user-123")  # Stored in tenant_a: namespace
user_b = container_b.subject("user-123")  # Stored in tenant_b: namespace
```

## Container Composition

Compose containers with subcontainers:

```python
from dependency_injector import containers, providers

class AppContainer(containers.DeclarativeContainer):
    """Application container"""

    # Configuration
    config = providers.Configuration()

    # Redis connection
    redis_client = providers.Singleton(
        redis.Redis.from_url,
        url=config.redis_url
    )

    # Create KRules sub-container
    krules = providers.Container(KRulesContainer)

    # Override KRules storage with Redis
    krules.subject_storage.override(
        providers.Callable(
            create_redis_storage,
            url=config.redis_url,
            key_prefix=config.key_prefix
        )
    )

# Use application container
app_container = AppContainer()
app_container.config.redis_url.from_env("REDIS_URL", default="redis://localhost:6379")
app_container.config.key_prefix.from_env("KEY_PREFIX", default="app:")

# Access KRules container
krules_container = app_container.krules()
on, when, middleware, emit = krules_container.handlers()
```

## Testing with Containers

Containers make testing easy:

### Test with Fresh Container

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.fixture
def container():
    """Create fresh container for each test"""
    return KRulesContainer()

@pytest.mark.asyncio
async def test_handler(container):
    on, when, middleware, emit = container.handlers()
    results = []

    @on("test.event")
    async def handler(ctx):
        results.append(ctx.event_type)

    user = container.subject("test-user")
    await emit("test.event", user)

    assert results == ["test.event"]
```

### Test with Custom Storage

```python
@pytest.fixture
async def container_with_redis():
    """Container with Redis storage"""
    container = KRulesContainer()

    from redis.asyncio import Redis
    redis_client = await create_redis_client("redis://localhost:6379")
    redis_factory = create_redis_storage(
        redis_client=redis_client,
        redis_prefix="test:"
    )
    container.subject_storage.override(providers.Object(redis_factory))

    return container

@pytest.mark.asyncio
async def test_with_redis(container_with_redis):
    user = container_with_redis.subject("user-123")
    await user.set("email", "test@example.com")
    await user.store()

    # Verify persistence
    user2 = container_with_redis.subject("user-123")
    assert await user2.get("email") == "test@example.com"
```

### Mock Dependencies

```python
from unittest.mock import Mock

@pytest.fixture
def container_with_mock():
    """Container with mocked storage"""
    container = KRulesContainer()

    # Create mock storage factory
    mock_storage = Mock()
    def mock_factory(name, **kwargs):
        return mock_storage
    container.subject_storage.override(providers.Object(mock_factory))

    return container, mock_storage

@pytest.mark.asyncio
async def test_with_mock(container_with_mock):
    container, mock_storage = container_with_mock

    user = container.subject("user-123")
    # Interact with mock storage...
```

## Configuration Patterns

### Environment-Based Configuration

```python
import os
from krules_core.container import KRulesContainer

async def create_container():
    """Create container with environment-based config"""
    container = KRulesContainer()

    # Configure storage based on environment
    storage_type = os.getenv("STORAGE_TYPE", "memory")

    if storage_type == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        redis_prefix = os.getenv("REDIS_KEY_PREFIX", "app:")

        from redis.asyncio import Redis
        redis_client = await create_redis_client(redis_url)
        redis_factory = create_redis_storage(redis_client, redis_prefix)
        container.subject_storage.override(providers.Object(redis_factory))

    return container

# Use in application
container = await create_container()
```

### Configuration Files

```python
import yaml
from krules_core.container import KRulesContainer

async def create_container_from_config(config_path):
    """Create container from YAML config"""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    container = KRulesContainer()

    # Configure storage
    if config.get("storage", {}).get("type") == "redis":
        redis_config = config["storage"]["redis"]
        from redis.asyncio import Redis
        redis_client = await create_redis_client(redis_config["url"])
        redis_factory = create_redis_storage(
            redis_client=redis_client,
            redis_prefix=redis_config.get("key_prefix", "")
        )
        container.subject_storage.override(providers.Object(redis_factory))

    return container

# config.yaml:
# storage:
#   type: redis
#   redis:
#     url: redis://localhost:6379
#     key_prefix: "myapp:"

container = await create_container_from_config("config.yaml")
```

## Advanced Patterns

### Singleton Container (Global)

```python
# container.py
from krules_core.container import KRulesContainer

# Global container instance
_container = None

def get_container():
    """Get or create global container"""
    global _container
    if _container is None:
        _container = KRulesContainer()
        # Configure container...
    return _container

# Use in modules
from .container import get_container

container = get_container()
on, when, middleware, emit = container.handlers()
```

### Factory Pattern

```python
async def create_production_container():
    """Create container for production"""
    container = KRulesContainer()

    from redis.asyncio import Redis
    redis_client = await create_redis_client(os.getenv("REDIS_URL"))
    redis_factory = create_redis_storage(
        redis_client=redis_client,
        redis_prefix=os.getenv("KEY_PREFIX")
    )
    container.subject_storage.override(providers.Object(redis_factory))

    return container

def create_test_container():
    """Create container for testing"""
    container = KRulesContainer()
    # Use default in-memory storage
    return container

# Use appropriate factory
if os.getenv("ENV") == "production":
    container = await create_production_container()
else:
    container = create_test_container()
```

## Best Practices

1. **One container per application** - Usually a singleton
2. **Configure at startup** - Override providers before using
3. **Don't pass container around** - Use it at application boundaries
4. **Fresh containers for tests** - Isolation between tests
5. **Environment-based config** - Different settings per environment
6. **Document overrides** - Explain why providers are overridden

## What's Next?

- [Storage Backends](STORAGE_BACKENDS.md) - Persistence layer
- [Testing](TESTING.md) - Testing strategies
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [API Reference](API_REFERENCE.md) - Complete API
