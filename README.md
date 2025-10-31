# KRules Framework

**Modern async-first event-driven application framework for Python**

KRules is a Python framework for building reactive, event-driven applications with a focus on dynamic state management and declarative event handling.

## Features

- **Reactive Subjects** - Dynamic entities with schema-less properties that automatically emit events on changes
- **Declarative Handlers** - Clean decorator-based API (`@on`, `@when`, `@middleware`)
- **Async Native** - Built on asyncio for high-performance concurrent event processing
- **Type Safe** - Full type hints for excellent IDE support and type checking
- **Dependency Injection** - Container-based architecture for testability and flexibility
- **Storage Agnostic** - Pluggable backends (Redis, SQLite, in-memory, custom)
- **Production Ready** - Middleware support, error isolation, monitoring hooks

## Installation

```bash
pip install krules-framework
```

With optional features:

```bash
# Redis storage backend
pip install "krules-framework[redis]"

# Google Cloud Pub/Sub
pip install "krules-framework[pubsub]"

# FastAPI integration
pip install "krules-framework[fastapi]"
```

## Quick Example

```python
from krules_core.container import KRulesContainer
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED
from datetime import datetime

# Initialize container
container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Define event handlers
@on("user.login")
@when(lambda ctx: ctx.subject.get("status") == "active")
async def handle_user_login(ctx):
    """Process active user login"""
    user = ctx.subject

    # Update properties (triggers property change events)
    user.set("last_login", datetime.now())
    user.set("login_count", lambda count: count + 1)

    # Emit new event
    await ctx.emit("user.logged-in", {
        "user_id": user.name,
        "count": user.get("login_count")
    })

# React to property changes
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_on_overheat(ctx):
    """Alert when temperature exceeds threshold"""
    await ctx.emit("alert.overheat", {
        "device": ctx.subject.name,
        "temperature": ctx.new_value
    })

# Use subjects
user = container.subject("user-123")
user.set("status", "active")
user.set("login_count", 0)

# Emit events
await emit("user.login", user, {"ip": "192.168.1.1"})
```

## Core Concepts

### Subjects - Reactive State Entities

Subjects are dynamic entities with persistent, reactive properties. Setting a property automatically emits a `subject-property-changed` event.

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()

# Create subject
device = container.subject("device-456")

# Set properties (schema-less, fully dynamic)
device.set("temperature", 75.5)
device.set("status", "online")
device.set("metadata", {"location": "room-1", "floor": 2})

# Lambda values for atomic operations
device.set("count", 0)
device.set("count", lambda c: c + 1)  # Atomic increment

# Get with defaults
temp = device.get("temperature")
status = device.get("status", default="offline")

# Extended properties (metadata, no events)
device.set_ext("tags", ["production", "critical"])

# Persist to storage
device.store()
```

### Event Handlers - Declarative Processing

Define handlers using decorators. Supports glob patterns and conditional filters.

```python
from krules_core.container import KRulesContainer
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Single event
@on("order.created")
async def process_order(ctx):
    ctx.subject.set("status", "processing")
    await ctx.emit("order.processing")

# Multiple events
@on("user.created", "user.updated", "user.deleted")
async def log_user_change(ctx):
    print(f"User event: {ctx.event_type}")

# Glob patterns
@on("device.*")
async def handle_device(ctx):
    print(f"Device event: {ctx.event_type}")

# Property change with filters
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "status")
@when(lambda ctx: ctx.new_value == "error")
async def on_error_status(ctx):
    await ctx.emit("alert.device_error", {
        "device_id": ctx.subject.name
    })
```

### Filters - Conditional Execution

Stack multiple `@when` decorators for conditional execution (all must pass).

```python
# Multiple filters (AND logic)
@on("payment.process")
@when(lambda ctx: ctx.payload.get("amount") > 0)
@when(lambda ctx: ctx.subject.get("verified") == True)
async def process_payment(ctx):
    # Only for verified users with amount > 0
    pass

# Reusable filters
def is_premium(ctx):
    return ctx.subject.get("tier") == "premium"

def has_credits(ctx):
    return ctx.subject.get("credits", 0) > 0

@on("feature.use")
@when(is_premium)
@when(has_credits)
async def use_premium_feature(ctx):
    ctx.subject.set("credits", lambda c: c - 1)
```

### Middleware - Cross-Cutting Concerns

Middleware runs for all events, enabling logging, timing, error handling, etc.

```python
from krules_core.container import KRulesContainer
import time

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

@middleware
async def timing_middleware(ctx, next):
    """Measure handler execution time"""
    start = time.time()
    await next()
    duration = time.time() - start
    print(f"{ctx.event_type} took {duration:.3f}s")

@middleware
async def error_handling(ctx, next):
    """Global error handler"""
    try:
        await next()
    except Exception as e:
        print(f"Handler error: {e}")
        await ctx.emit("error.handler_failed", {"error": str(e)})
```

## Storage Backends

KRules supports pluggable storage backends for subject persistence.

### Redis Storage

```python
from dependency_injector import providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import create_redis_storage

# Create container
container = KRulesContainer()

# Override storage with Redis
redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="myapp:"
)
container.subject_storage.override(providers.Object(redis_factory))

# Now all subjects use Redis
user = container.subject("user-123")
user.set("name", "John")  # Persisted in Redis
user.store()
```

### Custom Storage

Implement the storage interface to create custom backends:

```python
class CustomStorage:
    def __init__(self, subject_name, event_info=None, event_data=None):
        self._subject = subject_name

    def load(self):
        """Return (properties_dict, ext_properties_dict)"""
        return {}, {}

    def store(self, inserts=[], updates=[], deletes=[]):
        """Persist property changes"""
        pass

    def set(self, prop):
        """Set single property, return (new_value, old_value)"""
        pass

    def get(self, prop):
        """Get property value"""
        pass

    def delete(self, prop):
        """Delete property"""
        pass

    def flush(self):
        """Delete entire subject"""
        pass

    def get_ext_props(self):
        """Return extended properties dict"""
        return {}
```

## Testing

KRules provides utilities for easy testing:

```python
import pytest
from krules_core.container import KRulesContainer
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@pytest.fixture
def container():
    """Create fresh container for each test"""
    return KRulesContainer()

@pytest.mark.asyncio
async def test_user_login(container):
    """Test user login handler"""
    on, when, middleware, emit = container.handlers()
    results = []

    @on("user.login")
    async def handler(ctx):
        results.append(ctx.event_type)
        ctx.subject.set("logged_in", True)

    user = container.subject("test-user")
    await emit("user.login", user)

    assert len(results) == 1
    assert user.get("logged_in") == True
```

## Documentation

- [Quick Start Guide](QUICKSTART.md) - 5-minute tutorial
- [Core Concepts](CORE_CONCEPTS.md) - Framework fundamentals
- [Subjects](SUBJECTS.md) - Reactive property store deep dive
- [Event Handlers](EVENT_HANDLERS.md) - Handlers, filters, patterns
- [Middleware](MIDDLEWARE.md) - Cross-cutting concerns
- [Container & DI](CONTAINER_DI.md) - Dependency injection
- [Storage Backends](STORAGE_BACKENDS.md) - Persistence layer
- [Integrations](INTEGRATIONS.md) - FastAPI, Pub/Sub, CloudEvents
- [Testing](TESTING.md) - Testing strategies
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production best practices
- [Shell Mode](SHELL_MODE.md) - Interactive REPL usage
- [API Reference](API_REFERENCE.md) - Complete API documentation

## Integrations

### FastAPI

```python
from fastapi import FastAPI
from krules_fastapi_env import KRulesApp

app = FastAPI()
krules = KRulesApp(app)

@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = krules.container.subject(f"user-{user_id}")
    return user.dict()
```

### Google Cloud Pub/Sub

```python
from krules_cloudevents_pubsub import CloudEventsPubSubPublisher
from krules_core.container import KRulesContainer

container = KRulesContainer()
publisher = CloudEventsPubSubPublisher(
    project_id="my-project",
    topic_name="my-topic"
)

# Emit events to Pub/Sub
user = container.subject("user-123")
await publisher.publish("user.created", user, {"timestamp": "..."})
```

## Requirements

- Python >=3.11
- asyncio support

## License

Apache License 2.0

## Contributing

This framework is maintained by [Airspot](mailto:info@airspot.tech) for internal use, but contributions are welcome.

## Support

For issues and questions, please open a GitHub issue.

---

**Built with ❤️ by Airspot**
