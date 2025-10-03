# KRules Framework 2.0

KRules Framework is a modern, async-first event-driven application framework for Python.

## What's New in 2.0

🎉 **Complete rewrite** with focus on simplicity and developer experience:

- ✨ **Decorator-based API** - Clean, intuitive syntax
- ⚡ **Async/await native** - Built for modern Python
- 🎯 **Type hints** - Full IDE autocomplete support
- 🪶 **Lightweight** - Minimal dependencies (removed ReactiveX, Pydantic, CEL, JSONPath)
- 🧪 **Easy testing** - Simple, fast unit tests
- 📦 **Same subject system** - Dynamic properties, persistent state, storage backends

> **Note**: 2.0 has breaking changes. See [MIGRATION.md](MIGRATION.md) for upgrade guide.

## Quick Start

### Installation

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

### Basic Example

```python
from krules_core import on, when, emit, subject_factory
from datetime import datetime

# Define event handlers with decorators
@on("user.login")
@when(lambda ctx: ctx.subject.get("status") == "active")
async def handle_user_login(ctx):
    """Handle active user login"""
    user = ctx.subject

    # Update subject properties
    user.set("last_login", datetime.now())
    user.set("login_count", lambda count: count + 1)

    # Emit new events
    await ctx.emit("user.logged-in", {
        "user_id": user.name,
        "count": user.get("login_count")
    })

# React to property changes
@on("subject-property-changed")
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_on_overheat(ctx):
    """Alert when temperature exceeds threshold"""
    await ctx.emit("alert.overheat", {
        "device": ctx.subject.name,
        "temperature": ctx.new_value
    })

# Use subjects
user = subject_factory("user-123")
user.set("status", "active")
user.set("login_count", 0)

# Emit events
await emit("user.login", user, {"ip": "192.168.1.1"})
```

## Core Concepts

### Subjects - Dynamic Entities with State

Subjects are entities with persistent, reactive properties:

```python
from krules_core import subject_factory

# Create or load subject
device = subject_factory("device-456")

# Set properties (fully dynamic - no schema required!)
device.set("temperature", 75.5)
device.set("status", "online")
device.set("metadata", {"location": "room-1", "floor": 2})

# Get properties
temp = device.get("temperature")
status = device.get("status", default="offline")  # With default

# Lambda values (computed from previous value)
device.set("count", 0)
device.set("count", lambda c: c + 1)  # Increment

# Extended properties (metadata, not part of main state)
device.set_ext("tags", ["production", "critical"])

# Iteration
for prop_name in device:
    print(f"{prop_name}: {device.get(prop_name)}")

# Check existence
if "temperature" in device:
    print(device.get("temperature"))

# Persist to storage
device.store()

# Export to dict
data = device.dict()  # {"name": "device-456", "temperature": 75.5, ...}
```

### Event Handlers - Decorators

Define handlers using clean decorator syntax:

```python
from krules_core import on, when, EventContext

# Simple handler
@on("order.created")
async def process_order(ctx: EventContext):
    order = ctx.subject
    order.set("status", "processing")
    await ctx.emit("order.processing")

# Multiple events
@on("user.created", "user.updated", "user.deleted")
async def log_user_change(ctx: EventContext):
    logger.info(f"User event: {ctx.event_type}")

# Glob patterns
@on("device.*")  # Matches device.created, device.updated, etc.
async def handle_device(ctx: EventContext):
    process_device_event(ctx)

# Wildcard
@on("*")
async def log_all(ctx: EventContext):
    logger.debug(f"Event: {ctx.event_type} on {ctx.subject.name}")
```

### Filters - Conditional Execution

Use `@when` to add conditions:

```python
# Single filter
@on("payment.process")
@when(lambda ctx: ctx.payload.get("amount") > 0)
async def process_payment(ctx):
    # Only processes payments with amount > 0
    pass

# Multiple filters (ALL must pass)
@on("admin.action")
@when(lambda ctx: ctx.payload.get("role") == "admin")
@when(lambda ctx: ctx.subject.get("verified") == True)
@when(lambda ctx: not ctx.subject.get("suspended", False))
async def admin_action(ctx):
    # Only for verified, non-suspended admins
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
    # Use feature...
```

### Property Change Events

Subject properties emit change events automatically:

```python
@on("subject-property-changed")
@when(lambda ctx: ctx.property_name == "status")
async def on_status_change(ctx):
    device = ctx.subject
    print(f"Status changed: {ctx.old_value} → {ctx.new_value}")

    if ctx.new_value == "error":
        await ctx.emit("alert.device_error", {
            "device_id": device.name
        })

# Use it
device = subject_factory("device-123")
device.set("status", "ok")      # Emits subject-property-changed
device.set("status", "warning") # Emits subject-property-changed
device.set("status", "error")   # Emits subject-property-changed → triggers alert
```

### Middleware

Run logic for all events:

```python
from krules_core import middleware
import time

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
        logger.error(f"Handler error: {e}")
        await ctx.emit("error.handler_failed", {"error": str(e)})
```

## Advanced Features

### Storage Backends

```python
from dependency_injector import providers
from krules_core.providers import subject_storage_factory

# Redis storage
from redis_subjects_storage import RedisSubjectStorage
import redis

redis_client = redis.Redis(host='localhost', port=6379)
subject_storage_factory.override(
    providers.Factory(
        lambda name, **kwargs: RedisSubjectStorage(name, redis_client)
    )
)

# Now all subjects use Redis
user = subject_factory("user-123")
user.set("name", "John")  # Stored in Redis
```

### Async Context

```python
# In async context (FastAPI, async main, etc.)
@on("data.fetch")
async def fetch_data(ctx):
    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com/data")
        ctx.subject.set("external_data", response.json())

# Events emit asynchronously
await emit("data.fetch", subject)
```

### Testing

```python
import pytest
from krules_core import on, when, emit, subject_factory, reset_event_bus

@pytest.fixture(autouse=True)
def reset():
    """Reset event bus before each test"""
    reset_event_bus()

@pytest.mark.asyncio
async def test_user_login():
    """Test user login handler"""
    results = []

    @on("user.login")
    async def handler(ctx):
        results.append(ctx.event_type)
        ctx.subject.set("logged_in", True)

    user = subject_factory("test-user")
    await emit("user.login", user)

    assert len(results) == 1
    assert user.get("logged_in") == True
```

## Requirements

- Python >=3.11
- For async support: Python 3.11+ with asyncio

## Upgrading from 1.x

See [MIGRATION.md](MIGRATION.md) for detailed migration guide.

**TL;DR:**
1. Rules (`RuleFactory.create(...)`) → Handlers (`@on`, `@when`)
2. `event_router_factory().route()` → `await emit()`
3. `Filter`, `Process` classes → Python functions
4. Subject API unchanged ✅

## License

Apache License 2.0

## Contributing

This package is maintained by Airspot for internal use, but contributions are welcome.

---

Developed and maintained by [Airspot](mailto:info@airspot.tech)