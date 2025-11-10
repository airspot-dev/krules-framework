 # Migration Guide

This document covers two major migrations:
- **KRules 1.x → 2.0** - Complete rewrite with decorator-based API
- **KRules 2.0 → 3.0** - Async migration (see [MIGRATION_V3.md](MIGRATION_V3.md) for complete guide)

---

# Migration Guide: KRules 1.x → 2.0

## Overview

KRules 2.0 is a **complete rewrite** of the framework with breaking changes.
The new version focuses on:

- ✅ Simpler, decorator-based API
- ✅ Async/await native support
- ✅ Better type hints and IDE support
- ✅ Reduced dependencies (removed ReactiveX, Pydantic, cel-python, etc.)
- ✅ Cleaner, more maintainable codebase

**What's preserved:**
- ✅ Subject system (dynamic properties, storage, caching)
- ✅ Property change events
- ✅ Storage backends (EmptyStorage compatible, Redis/SQLite need updates)

**What's removed:**
- ❌ Rule-based system (RuleFactory, Rule, RuleConst)
- ❌ Base functions (filters, processing)
- ❌ Arg processors
- ❌ ReactiveX dependency
- ❌ Pydantic models for rules
- ❌ CEL expressions
- ❌ JSON

Path support

## Breaking Changes

### 1. Rule definitions → Event handlers

**Before (1.x):**
```python
from krules_core.core import RuleFactory
from krules_core.base_functions.filters import CheckSubjectProperty
from krules_core.base_functions.processing import SetSubjectProperty, Route

rulesdata = [
    {
        "name": "on-user-login",
        "subscribe_to": "user.login",
        "data": {
            "filters": [
                CheckSubjectProperty("status", value="active")
            ],
            "processing": [
                SetSubjectProperty("last_login", lambda: datetime.now()),
                Route("user.logged-in")
            ]
        }
    }
]

for rule in rulesdata:
    RuleFactory.create(**rule)
```

**After (2.0):**
```python
from krules_core import on, when, subject_factory

@on("user.login")
@when(lambda ctx: ctx.subject.get("status") == "active")
async def handle_user_login(ctx):
    user = ctx.subject
    user.set("last_login", datetime.now())
    await ctx.emit("user.logged-in")
```

### 2. Event routing

**Before (1.x):**
```python
from krules_core.providers import event_router_factory, subject_factory

router = event_router_factory()
subject = subject_factory("user-123")
router.route("user.login", subject, {"ip": "1.2.3.4"})
```

**After (2.0):**
```python
from krules_core import emit, subject_factory

subject = subject_factory("user-123")
await emit("user.login", subject, {"ip": "1.2.3.4"})
```

### 3. Subject usage (mostly unchanged!)

**Before (1.x):**
```python
from krules_core.providers import subject_factory

user = subject_factory("user-123")
user.set("name", "John")
user.set("age", 30)
user.set("count", lambda c: c + 1)  # Lambda still works!
value = user.get("name")
```

**After (2.0):**
```python
from krules_core import subject_factory

user = subject_factory("user-123")
user.set("name", "John")
user.set("age", 30)
user.set("count", lambda c: c + 1)  # Same API!
value = user.get("name")
```

✅ **Subject API is 100% compatible!**

### 4. Property change events

**Before (1.x):**
```python
from krules_core.base_functions.filters import OnSubjectPropertyChanged
from krules_core import event_types

rulesdata = [{
    "name": "on-temp-change",
    "subscribe_to": event_types.SUBJECT_PROPERTY_CHANGED,
    "data": {
        "filters": [OnSubjectPropertyChanged("temperature")],
        "processing": [...]
    }
}]
```

**After (2.0):**
```python
from krules_core import on, when

@on("subject-property-changed")
@when(lambda ctx: ctx.property_name == "temperature")
async def on_temp_change(ctx):
    print(f"Temperature changed: {ctx.old_value} → {ctx.new_value}")
```

### 5. Filters and processing

**Before (1.x):**
```python
from krules_core.base_functions.filters import Filter, PayloadMatch
from krules_core.base_functions.processing import Process, SetSubjectProperty

{
    "filters": [
        Filter(lambda payload: payload.get("valid") == True),
        PayloadMatch("$.user.role", "admin")
    ],
    "processing": [
        SetSubjectProperty("processed", True),
        Process(lambda self: custom_logic(self.subject))
    ]
}
```

**After (2.0):**
```python
@on("my.event")
@when(lambda ctx: ctx.payload.get("valid") == True)
@when(lambda ctx: ctx.payload.get("user", {}).get("role") == "admin")
async def handle(ctx):
    ctx.subject.set("processed", True)
    await custom_logic(ctx.subject)
```

## Migration Strategy

### Step 1: Update dependencies

```bash
pip install --upgrade krules-framework>=2.0.0
```

### Step 2: Convert rules one by one

For each rule in your `rulesdata`:

1. **Extract event type** from `subscribe_to`
2. **Convert filters** to `@when` decorators
3. **Convert processing** to function body
4. **Add `async def` and `@on` decorator**

### Step 3: Update imports

**Remove:**
```python
from krules_core.core import RuleFactory
from krules_core.base_functions.filters import *
from krules_core.base_functions.processing import *
from krules_core.providers import event_router_factory
from krules_core import event_types, RuleConst
```

**Add:**
```python
from krules_core import on, when, emit, subject_factory, EventContext
```

### Step 4: Update event emission

Replace:
```python
event_router_factory().route(event_type, subject, payload)
```

With:
```python
await emit(event_type, subject, payload)
```

Or inside handlers:
```python
await ctx.emit(event_type, payload)
```

## Common Patterns

### Pattern 1: Simple event handler

**Before:**
```python
{
    "name": "greet-user",
    "subscribe_to": "user.created",
    "data": {
        "processing": [
            SetSubjectProperty("greeted", True),
            Route("welcome.email")
        ]
    }
}
```

**After:**
```python
@on("user.created")
async def greet_user(ctx):
    ctx.subject.set("greeted", True)
    await ctx.emit("welcome.email")
```

### Pattern 2: Filtered handler

**Before:**
```python
{
    "name": "premium-feature",
    "subscribe_to": "feature.use",
    "data": {
        "filters": [CheckSubjectProperty("tier", value="premium")],
        "processing": [Process(lambda self: use_feature(self.subject))]
    }
}
```

**After:**
```python
@on("feature.use")
@when(lambda ctx: ctx.subject.get("tier") == "premium")
async def premium_feature(ctx):
    await use_feature(ctx.subject)
```

### Pattern 3: Property watching

**Before:**
```python
{
    "name": "alert-on-overheat",
    "subscribe_to": "subject-property-changed",
    "data": {
        "filters": [
            OnSubjectPropertyChanged("temperature", value=lambda v: v > 80)
        ],
        "processing": [Route("alert.overheat")]
    }
}
```

**After:**
```python
@on("subject-property-changed")
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_overheat(ctx):
    await ctx.emit("alert.overheat", {
        "device": ctx.subject.name,
        "temp": ctx.new_value
    })
```

### Pattern 4: Wildcard rules

**Before:**
```python
{
    "name": "log-all",
    "subscribe_to": "*",
    "data": {
        "processing": [Process(lambda self: logger.info(self.event_type))]
    }
}
```

**After:**
```python
@on("*")
async def log_all(ctx):
    logger.info(f"Event: {ctx.event_type}")
```

### Pattern 5: Glob patterns

**Before:**
```python
{
    "name": "handle-device-events",
    "subscribe_to": ["device.created", "device.updated", "device.deleted"],
    ...
}
```

**After:**
```python
@on("device.*")  # Glob pattern!
async def handle_device_events(ctx):
    print(f"Device event: {ctx.event_type}")
```

## API Reference

### Event Handlers

```python
@on(*event_patterns: str)
```
Register handler for one or more event patterns. Supports globs.

```python
@when(*conditions: Callable[[EventContext], bool])
```
Add filter conditions (all must pass). Can be stacked.

```python
@middleware
async def my_middleware(ctx: EventContext, next: Callable)
```
Run for all events. Control execution with `await next()`.

### Event Context

```python
class EventContext:
    event_type: str          # Event type
    subject: Subject         # Subject instance
    payload: dict           # Event payload
    property_name: str      # For property change events
    old_value: Any          # For property change events
    new_value: Any          # For property change events

    async def emit(event_type, payload=None, subject=None)
```

### Subjects

Subject API is **unchanged** from 1.x:

```python
subject = subject_factory("name")
subject.set(prop, value, muted=False, use_cache=None)
subject.get(prop, use_cache=None, default=None)
subject.delete(prop, muted=False)
subject.set_ext(prop, value)
subject.get_ext(prop)
subject.store()
subject.flush()
subject.dict()
```

## Module Changes and Removals

### PubSub Integration: krules_pubsub → krules_cloudevents_pubsub

The separate `krules_pubsub` module has been **merged** into `krules_cloudevents_pubsub` with a modern container-first architecture.

**Before (1.x):**
```python
from krules_pubsub.subscriber import PubSubSubscriber

subscriber = PubSubSubscriber()
subscriber.start()
```

**After (2.0):**
```python
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import PubSubSubscriber

# Initialize container
container = KRulesContainer()

# Create subscriber with dependency injection
subscriber = PubSubSubscriber(
    event_bus=container.event_bus(),
    subject_factory=container.subject,
)

# Define handlers using decorators
on, when, middleware, emit = container.handlers()

@on("order.created")
async def handle_order(ctx):
    print(f"Order: {ctx.subject.name}")

# Start subscriber
await subscriber.start()
```

**Import changes:**
- ❌ `from krules_pubsub.subscriber import PubSubSubscriber`
- ✅ `from krules_cloudevents_pubsub import PubSubSubscriber`

### krules_env Removed

The `krules_env` module has been **completely removed**. It was a legacy initialization layer that is no longer needed with KRulesContainer.

**Before (1.x):**
```python
# app.py
from krules_env import init

init()  # Magic global initialization

# ruleset.py
rulesdata = [...]  # Rules auto-loaded by krules_env
```

**After (2.0):**
```python
# main.py - Explicit initialization
from krules_core.container import KRulesContainer

# Create container
container = KRulesContainer()

# Get handler decorators
on, when, middleware, emit = container.handlers()

# Define handlers in the same file or import them
@on("user.created")
async def handle_user(ctx):
    ctx.subject.set("processed", True)

# Application startup
if __name__ == "__main__":
    # Your application logic here
    # Handlers are already registered via decorators
    pass
```

**What replaced it:**
- ❌ `krules_env.init()` - Use `KRulesContainer()` explicitly
- ❌ Automatic ruleset loading - Use `@on`/`@when` decorators
- ❌ Global state - Use container instance
- ❌ Settings from `/krules/config` - Load settings directly in your code

### Container-First Architecture

KRules 2.0 uses **dependency injection** via `KRulesContainer` instead of global factory patterns.

**Before (1.x):**
```python
from krules_core.providers import subject_factory, event_router_factory, configs_factory

# Global factories
subject = subject_factory("user-123")
router = event_router_factory()
configs = configs_factory()
```

**After (2.0):**
```python
from krules_core.container import KRulesContainer

# Create container instance
container = KRulesContainer()

# Get dependencies from container
subject = container.subject("user-123")
event_bus = container.event_bus()
on, when, middleware, emit = container.handlers()

# Or use standalone functions (they use global container)
from krules_core import subject_factory, emit
subject = subject_factory("user-123")
await emit("event.type", subject, {})
```

**Benefits:**
- ✅ Explicit dependencies (no magic globals)
- ✅ Easier testing (inject mocks via container)
- ✅ Multiple containers in same process
- ✅ Clear lifecycle management

### CloudEvents Dispatchers

Both HTTP and PubSub dispatchers now use modern middleware patterns.

**HTTP Dispatcher (krules_cloudevents):**
```python
from krules_core.container import KRulesContainer
from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware

container = KRulesContainer()

# Create HTTP dispatcher
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://api.example.com/events",
    source="my-service",
    krules_container=container,
)

# Register middleware for transparent dispatch
middleware_func = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(middleware_func)

# Use in handlers
on, when, middleware, emit = container.handlers()

@on("order.created")
async def handle_order(ctx):
    # Dispatch to external HTTP endpoint
    await ctx.emit(
        "order.confirmed",
        {"amount": 100},
        ctx.subject,
        dispatch_url="https://external-service.com/events"
    )
```

**PubSub Dispatcher (krules_cloudevents_pubsub):**
```python
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import CloudEventsDispatcher, create_dispatcher_middleware

container = KRulesContainer()

# Create PubSub dispatcher
dispatcher = CloudEventsDispatcher(
    project_id="my-project",
    source="my-service",
    krules_container=container,
)

# Register middleware
middleware_func = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(middleware_func)

# Use in handlers
on, when, middleware, emit = container.handlers()

@on("order.created")
async def handle_order(ctx):
    # Publish to PubSub topic
    await ctx.emit(
        "order.confirmed",
        {"amount": 100},
        ctx.subject,
        topic="projects/my-project/topics/orders"
    )
```

**Dispatch policies:**
- `DispatchPolicyConst.DIRECT` (default): External dispatch only, skip local handlers
- `DispatchPolicyConst.BOTH`: External dispatch AND execute local handlers

## Removed Features

- `RuleFactory.create()` - Use `@on` decorator
- `RuleConst` - Use string literals
- `event_types.*` - Use string literals ("subject-property-changed")
- `Filter`, `Process` classes - Use `@when` and function body
- `PayloadMatch`, `SubjectNameMatch` - Use lambdas
- `SetSubjectProperty`, `SetPayloadProperty` - Use `ctx.subject.set()`, `ctx.payload[key] = value`
- `Route` - Use `await ctx.emit()`
- `event_router_factory` - Use `emit()` function or `container.event_bus()`
- `proc_events_rx_factory` - No longer needed (use middleware for observability)
- `krules_env` module - Use `KRulesContainer()` explicitly
- `krules_pubsub` module - Merged into `krules_cloudevents_pubsub`
- CEL expressions - Use Python lambdas
- JSONPath in rules - Use Python dict access

## Dependencies Removed

- `reactivex` (ReactiveX) - Replaced with async/await
- `pydantic` - No longer needed for rules
- `cel-python` - Use Python expressions
- `jsonpath-rw-ext` - Use native dict access
- `jsonpatch` - Removed
- `pytz` - Use `datetime.timezone`
- `deepmerge` - No longer needed

## What Next?

1. Review your current rules
2. Start converting high-value rules first
3. Test thoroughly (behavior might differ in edge cases)
4. Update your deployment/configuration
5. Monitor for issues

---

# Migration Guide: KRules 2.0 → 3.0 (Async)

## Overview

KRules 3.0 is a **full async migration** with breaking changes to the Subject and storage APIs.

**What changed:**
- ✅ All Subject persistence methods are now async
- ✅ All handlers must be `async def`
- ✅ All storage backends are async
- ✅ Filters can be async
- ✅ Middleware is async-only

**What's preserved:**
- ✅ Subject property access (cache mode) remains sync
- ✅ Event system architecture unchanged
- ✅ Decorator-based API unchanged
- ✅ Container and DI patterns unchanged

**Complete migration guide:** See [MIGRATION_V3.md](MIGRATION_V3.md) for detailed instructions, code examples, and migration checklist.

## Quick Summary of Breaking Changes

### 1. Subject Methods → Async

**Before (2.0 - sync):**
```python
user = container.subject("user-123")
user.set("email", "john@example.com")
email = user.get("email")
user.delete("temp")
user.store()
```

**After (3.0 - async):**
```python
user = container.subject("user-123")
await user.set("email", "john@example.com")
email = await user.get("email")
await user.delete("temp")
await user.store()
```

### 2. Handlers → Async Only

**Before (2.0 - sync or async):**
```python
@on("user.login")
def handle_login(ctx):  # Sync handler worked
    ctx.subject.set("last_login", datetime.now())
```

**After (3.0 - async only):**
```python
@on("user.login")
async def handle_login(ctx):  # Must be async
    await ctx.subject.set("last_login", datetime.now())
```

### 3. Storage Interface → Async

**Before (2.0 - sync):**
```python
class MyStorage(SubjectStorage):
    def load(self):
        return props, ext_props

    def store(self, inserts, updates, deletes):
        # Sync storage operations
        pass
```

**After (3.0 - async):**
```python
class MyStorage(SubjectStorage):
    async def load(self):
        return props, ext_props

    async def store(self, inserts, updates, deletes):
        # Async storage operations
        pass
```

### 4. Redis Storage → redis.asyncio

**Before (2.0 - sync):**
```python
from redis import Redis
from redis_subjects_storage import create_redis_storage

redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="app:"
)
```

**After (3.0 - async):**
```python
from redis.asyncio import Redis
from redis_subjects_storage import create_redis_client, create_redis_storage

redis_client = await create_redis_client("redis://localhost:6379")
redis_factory = create_redis_storage(
    redis_client=redis_client,
    redis_prefix="app:"
)
```

## Migration Steps

1. **Update all handlers to `async def`**
   - Search for: `@on(` followed by `def `
   - Replace with: `async def`

2. **Add `await` to all Subject methods**
   - `subject.set()` → `await subject.set()`
   - `subject.get()` → `await subject.get()`
   - `subject.delete()` → `await subject.delete()`
   - `subject.store()` → `await subject.store()`
   - `subject.flush()` → `await subject.flush()`
   - `subject.set_ext()` → `await subject.set_ext()`
   - `subject.get_ext()` → `await subject.get_ext()`

3. **Update storage backend**
   - Redis: Use `redis.asyncio`
   - Custom storage: Implement async methods

4. **Update tests**
   - Add `@pytest.mark.asyncio` to all test functions
   - Make test functions `async def`
   - Add `await` to all Subject operations

5. **Update integrations**
   - Pub/Sub dispatcher: Already async
   - FastAPI: Already async
   - CloudEvents: Update to async dispatch

## What Next?

1. Read the complete migration guide: [MIGRATION_V3.md](MIGRATION_V3.md)
2. Review the async/sync integration patterns: [ASYNC_IN_SYNC.md](ASYNC_IN_SYNC.md)
3. Update your codebase following the migration checklist
4. Test thoroughly
5. Monitor for issues

## Support

For questions or issues: https://github.com/airspot-dev/krules-framework/issues