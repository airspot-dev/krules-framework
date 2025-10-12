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

## Removed Features

- `RuleFactory.create()` - Use `@on` decorator
- `RuleConst` - Use string literals
- `event_types.*` - Use string literals ("subject-property-changed")
- `Filter`, `Process` classes - Use `@when` and function body
- `PayloadMatch`, `SubjectNameMatch` - Use lambdas
- `SetSubjectProperty`, `SetPayloadProperty` - Use `ctx.subject.set()`, `ctx.payload[key] = value`
- `Route` - Use `await ctx.emit()`
- `event_router_factory` - Use `emit()` function
- `proc_events_rx_factory` - No longer needed (use middleware for observability)
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

## Support

For questions or issues: https://github.com/airspot-dev/krules-framework/issues