# KRules Framework

**Modern async-first event-driven application framework for Python**

KRules is a Python framework for building reactive, event-driven applications with a focus on dynamic state management and declarative event handling.

## Features

- **Reactive Subjects** - Dynamic entities with schema-less properties that automatically emit events on changes
- **Declarative Handlers** - Clean decorator-based API (`@on`, `@when`, `@middleware`)
- **Async Native** - Built on asyncio for high-performance concurrent event processing
- **Type Safe** - Full type hints for excellent IDE support and type checking
- **Dependency Injection** - Container-based architecture for testability and flexibility
- **Storage Agnostic** - Pluggable backends (Redis, PostgreSQL, in-memory, custom)
- **Production Ready** - Middleware support, error isolation, monitoring hooks

## Installation

```bash
pip install krules-framework
```

With optional features:

```bash
# Redis storage backend
pip install "krules-framework[redis]"

# PostgreSQL storage backend
pip install "krules-framework[postgres]"

# Google Cloud Pub/Sub
pip install "krules-framework[pubsub]"

# FastAPI integration
pip install "krules-framework[fastapi]"
```

## Quick Example

This example demonstrates **reactive state composition** - building complex states from simple properties, where each layer reacts to changes in lower layers.

```python
from krules_core.container import KRulesContainer
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Layer 1: Derive health status from metrics (ONLY for device: subjects)
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.subject.name.startswith("device:"))
@when(lambda ctx: ctx.property_name in ["cpu_usage", "memory_usage", "error_rate"])
async def compute_device_health(ctx):
    """Aggregate device metrics into health status"""
    device = ctx.subject
    # Read from subject's internal cache (even if not yet persisted)
    cpu = device.get("cpu_usage", 0)
    memory = device.get("memory_usage", 0)
    errors = device.get("error_rate", 0)

    if cpu > 90 or memory > 90 or errors > 10:
        device.set("health", "critical")
    elif cpu > 70 or memory > 70 or errors > 5:
        device.set("health", "warning")
    else:
        device.set("health", "healthy")

# Layer 2: React to health transitions (ONLY for device: subjects)
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.subject.name.startswith("device:"))
@when(lambda ctx: ctx.property_name == "health")
async def handle_device_health_change(ctx):
    """Take action based on health state transition"""
    print(f"{ctx.subject.name}: {ctx.old_value} → {ctx.new_value}")

    if ctx.new_value == "critical":
        await ctx.emit("device.alert.critical", ctx.subject)
    elif ctx.new_value == "healthy" and ctx.old_value == "critical":
        await ctx.emit("device.alert.recovered", ctx.subject)

# Usage
device = container.subject("device:prod-01")

# Batch mode: multiple sets + single store
device.set("cpu_usage", 75)      # → triggers handler, health="warning"
device.set("memory_usage", 60)
device.set("error_rate", 2)
device.store()  # Single persistence, flushes cache to storage

# Single update mode: bypass cache, write directly
await device.set("cpu_usage", 95, use_cache=False)  # → health="critical" → alert!
await device.set("cpu_usage", 50, use_cache=False)  # → health="healthy" → recovered!
await device.set("cpu_usage", 45, use_cache=False)  # → NO EVENT (health unchanged)
```

**Key Concepts:**

1. **Reactive Composition** - `health` state is automatically derived from metrics
2. **Subject Type Filtering** - Handlers target `device:*` subjects using naming conventions
3. **Events on Change Only** - Property change events fire only when values actually change
4. **State Transitions** - Access `old_value` and `new_value` to handle transitions
5. **Efficient Persistence** - Batch updates with single `store()`, or `use_cache=False` for single updates
6. **Bounded Entities** - Devices are predictable, limited entities (not infinite like orders)

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

# Pass extra context to handlers (audit trail, business context)
await device.set("status", "maintenance", extra={
    "reason": "scheduled_maintenance",
    "operator_id": "admin-123"
})

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

# Access extra context from set() operations
@on(SUBJECT_PROPERTY_CHANGED)
async def audit_property_change(ctx):
    if ctx.extra:  # Extra context passed from set()/delete()
        operator = ctx.extra.get("operator_id", "system")
        reason = ctx.extra.get("reason", "unspecified")
        print(f"{operator} changed {ctx.property_name}: {reason}")
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
from redis.asyncio import Redis
from redis_subjects_storage.storage_impl import create_redis_storage

# Create container
container = KRulesContainer()

# Create Redis client
redis_client = Redis.from_url("redis://localhost:6379")

# Override storage with Redis
redis_factory = create_redis_storage(
    redis_client=redis_client,
    redis_prefix="myapp:"
)
container.subject_storage.override(providers.Object(redis_factory))

# Now all subjects use Redis
user = container.subject("user-123")
await user.set("name", "John")  # Persisted in Redis
await user.store()
```

### PostgreSQL Storage

```python
from dependency_injector import providers
from krules_core.container import KRulesContainer
import asyncpg
from postgres_subjects_storage.storage_impl import create_postgres_storage

# Create container
container = KRulesContainer()

# Create PostgreSQL connection pool
pg_pool = await asyncpg.create_pool(
    database="krules",
    user="postgres",
    password="postgres",
    host="localhost",
    port=5432
)

# Override storage with PostgreSQL
pg_factory = create_postgres_storage(pool=pg_pool)
container.subject_storage.override(providers.Object(pg_factory))

# Now all subjects use PostgreSQL (tables auto-created)
user = container.subject("user-123")
await user.set("name", "John")  # Persisted in PostgreSQL with JSONB
await user.store()
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

- [Quick Start Guide](docs/QUICKSTART.md) - 5-minute tutorial
- [Core Concepts](docs/CORE_CONCEPTS.md) - Framework fundamentals
- [Subjects](docs/SUBJECTS.md) - Reactive property store deep dive
- [Event Handlers](docs/EVENT_HANDLERS.md) - Handlers, filters, patterns
- [Middleware](docs/MIDDLEWARE.md) - Cross-cutting concerns
- [Container & DI](docs/CONTAINER_DI.md) - Dependency injection
- [Storage Backends](docs/STORAGE_BACKENDS.md) - Persistence layer
- [Integrations](docs/INTEGRATIONS.md) - FastAPI, Pub/Sub, CloudEvents
- [Testing](docs/TESTING.md) - Testing strategies
- [Advanced Patterns](docs/ADVANCED_PATTERNS.md) - Production best practices
- [API Reference](docs/API_REFERENCE.md) - Complete API documentation

## Integrations

KRules supports event-driven communication with external systems through **event receivers** (inbound) and **event emitters** (outbound).

### Event Receivers (Inbound)

**FastAPI Integration** - Receive HTTP CloudEvents

```python
from krules_fastapi_env import KRulesApp
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Define handlers (same as local events)
@on("order.created")
async def handle_order(ctx):
    print(f"Received order: {ctx.subject.name}")

# Create FastAPI app that receives CloudEvents
app = KRulesApp(krules_container=container)
# POST /krules endpoint now receives CloudEvents and triggers handlers
```

**Pub/Sub Subscriber** - Receive events from Google Pub/Sub

```python
from krules_cloudevents_pubsub import PubSubSubscriber

# Subscribe to Pub/Sub topic
subscriber = PubSubSubscriber(
    project_id="my-project",
    subscription_name="my-subscription",
    container=container
)

# Same handlers work for Pub/Sub events
await subscriber.run()
```

### Event Emitters (Outbound)

**HTTP CloudEvents** - Send events to external HTTP endpoints

```python
from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware

# Create dispatcher
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://api.example.com/events",
    source="my-service",
    krules_container=container
)

# Register as middleware
dispatcher_mw = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(dispatcher_mw)

# Now emit events to external URL
await emit("user.created", user, dispatch_url="https://api.example.com/events")
```

**Pub/Sub Publisher** - Send events to Google Pub/Sub

```python
from krules_cloudevents_pubsub import CloudEventsDispatcher, create_dispatcher_middleware

# Create dispatcher
dispatcher = CloudEventsDispatcher(
    project_id="my-project",
    default_topic="krules-events",
    source="my-service",
    krules_container=container
)

# Register as middleware
dispatcher_mw = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(dispatcher_mw)

# Emit to Pub/Sub topic
await emit("user.created", user, topic="user-events")
```

See [Integrations](docs/INTEGRATIONS.md) for detailed guides.

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
