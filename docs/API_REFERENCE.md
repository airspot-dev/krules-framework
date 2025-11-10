# API Reference

Complete API reference for KRules Framework.

## krules_core.container

### KRulesContainer

```python
class KRulesContainer(containers.DeclarativeContainer)
```

Dependency injection container managing all KRules components.

**Providers:**
- `event_bus`: Singleton EventBus instance
- `subject_storage`: Callable factory for storage backends
- `subject`: Factory for creating Subject instances
- `handlers`: Callable returning (on, when, middleware, emit)

**Methods:**

#### `subject(name: str, event_info=None, event_data=None) -> Subject`

Create or retrieve a subject.

**Parameters:**
- `name` (str): Subject identifier
- `event_info` (dict, optional): Event information context
- `event_data` (any, optional): Event data context

**Returns:** Subject instance

**Example:**
```python
container = KRulesContainer()
user = container.subject("user-123")
await user.set("email", "john@example.com")
```

#### `handlers() -> tuple[Callable, Callable, Callable, Callable]`

Get handler decorators and emit function.

**Returns:** Tuple of (on, when, middleware, emit)

**Example:**
```python
on, when, middleware, emit = container.handlers()
```

**See:** [Container & DI](CONTAINER_DI.md)

---

## krules_core.subject

### Subject

```python
class Subject
```

Dynamic entity with reactive properties.

**Methods:**

#### `async set(prop: str, value: Any, muted: bool = False, extra: dict | None = None) -> tuple[Any, Any]`

Set property value (async).

**Parameters:**
- `prop` (str): Property name
- `value` (Any | Callable): Value or lambda function
- `muted` (bool): If True, don't emit property change event
- `extra` (dict | None): Optional context dict passed to event handlers

**Returns:** tuple[(new_value, old_value)]

**Example:**
```python
await user.set("email", "john@example.com")
await user.set("counter", lambda c: c + 1)
await user.set("internal", 0, muted=True)
await user.set("status", "suspended", extra={"reason": "policy_violation"})
```

#### `async get(prop: str, use_cache: bool | None = None, default: Any = None) -> Any`

Get property value (async).

**Parameters:**
- `prop` (str): Property name
- `use_cache` (bool | None): Override caching behavior
- `default` (Any): Default value if property doesn't exist

**Returns:** Property value

**Raises:** AttributeError if property doesn't exist and no default

**Example:**
```python
email = await user.get("email")
status = await user.get("status", default="inactive")
```

#### `async delete(prop: str, muted: bool = False, extra: dict | None = None) -> None`

Delete property (async).

**Parameters:**
- `prop` (str): Property name
- `muted` (bool): If True, don't emit property deleted event
- `extra` (dict | None): Optional context dict passed to event handlers

**Returns:** None

**Example:**
```python
await user.delete("temp_token")
await user.delete("cache", extra={"reason": "expired"})
```

#### `async set_ext(prop: str, value: Any, use_cache: bool | None = None) -> tuple[Any, Any]`

Set extended property (metadata, no events - async).

#### `async get_ext(prop: str, use_cache: bool | None = None, default: Any = None) -> Any`

Get extended property (async).

#### `async delete_ext(prop: str, use_cache: bool | None = None) -> None`

Delete extended property (async).

#### `async store() -> None`

Persist cached changes to storage (async).

#### `async flush() -> None`

Delete entire subject from storage and emit deletion events (async).

#### `async dict() -> dict`

Export subject to dictionary (async).

**Returns:** Dict with name, properties, and extended properties

**Example:**
```python
data = await user.dict()
# {"name": "user-123", "email": "john@example.com", "ext": {...}}
```

**Magic Methods:**
- `__contains__(item)`: Check if property exists (`"email" in user`)
- `__iter__()`: Iterate over property names (`for prop in user`)
- `__len__()`: Get property count (`len(user)`)

**See:** [Subjects](SUBJECTS.md)

---

## krules_core.event_bus

### EventBus

```python
class EventBus
```

Event routing and handler management.

**Methods:**

#### `register(func: Callable, event_patterns: list[str], filters: list[Callable] | None = None) -> Handler`

Register event handler.

**Parameters:**
- `func` (Callable): Handler function
- `event_patterns` (list[str]): Event patterns to match
- `filters` (list[Callable] | None): Optional filter functions

**Returns:** Handler instance

#### `async emit(event_type: str, subject: Any, payload: dict, extra: dict | None = None, **kwargs) -> None`

Emit event to all matching handlers (async).

**Parameters:**
- `event_type` (str): Event type
- `subject` (Subject): Subject instance
- `payload` (dict): Event payload
- `extra` (dict | None): Extra context dict passed to handlers (accessible via ctx.extra)
- `**kwargs`: Additional metadata (stored in ctx._metadata)

#### `add_middleware(middleware: Callable) -> None`

Add middleware function.

**See:** [Event Handlers](EVENT_HANDLERS.md), [Middleware](MIDDLEWARE.md)

### EventContext

```python
@dataclass
class EventContext
```

Context passed to handlers.

**Attributes:**
- `event_type` (str): Event type
- `subject` (Subject): Subject instance
- `payload` (dict): Event payload
- `extra` (dict | None): Extra context dict passed from set()/delete() operations
- `property_name` (str | None): Property name (for property change events)
- `old_value` (Any | None): Old value (for property change events)
- `new_value` (Any | None): New value (for property change events)

**Methods:**

#### `async emit(event_type: str, payload: dict | None = None, subject: Any | None = None, **extra) -> None`

Emit new event from handler (async).

#### `get_metadata(key: str, default: Any = None) -> Any`

Get metadata value.

#### `set_metadata(key: str, value: Any) -> None`

Set metadata value.

**See:** [Event Handlers](EVENT_HANDLERS.md)

---

## krules_core.handlers

### on(*patterns: str)

Decorator to register event handler.

**Parameters:**
- `*patterns` (str): Event patterns (exact, glob, wildcard)

**Returns:** Decorator function

**Example:**
```python
@on("user.login")
@on("device.*")
@on("*")
async def handler(ctx): pass
```

### when(*conditions: Callable)

Decorator to add conditional filters.

**Parameters:**
- `*conditions` (Callable): Filter functions returning bool

**Returns:** Decorator function

**Example:**
```python
@on("user.action")
@when(lambda ctx: ctx.subject.get("status") == "active")
async def handler(ctx): pass
```

### middleware(func: Callable)

Decorator to register middleware.

**Parameters:**
- `func` (Callable): Middleware function with signature `async def mw(ctx, next)`

**Returns:** Decorated function

**Example:**
```python
@middleware
async def log_middleware(ctx, next):
    print(f"Event: {ctx.event_type}")
    await next()
```

### async emit(event_type: str, subject: Any, payload: dict | None = None, **extra)

Emit event directly (outside handlers - async).

**Parameters:**
- `event_type` (str): Event type
- `subject` (Subject): Subject instance
- `payload` (dict | None): Event payload
- `**extra`: Additional metadata

**Example:**
```python
await emit("user.action", user, {"data": "value"})
```

**See:** [Event Handlers](EVENT_HANDLERS.md), [Middleware](MIDDLEWARE.md)

---

## krules_core.event_types

### Constants

```python
SUBJECT_PROPERTY_CHANGED = "subject-property-changed"
SUBJECT_PROPERTY_DELETED = "subject-property-deleted"
SUBJECT_DELETED = "subject-deleted"
```

Built-in event type constants.

**Example:**
```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
async def on_property_change(ctx):
    print(f"{ctx.property_name} changed")
```

---

## Storage Interface

### SubjectStorage (Interface)

```python
class SubjectStorage
```

Interface for storage backends.

**Methods:**

#### `async load() -> tuple[dict, dict]`

Load subject state from storage (async).

**Returns:** (properties_dict, ext_properties_dict)

#### `async store(inserts: list = [], updates: list = [], deletes: list = []) -> None`

Persist property changes in batch (async).

#### `async set(prop: SubjectProperty) -> tuple[Any, Any]`

Set single property atomically (async).

**Returns:** (new_value, old_value)

#### `async get(prop: SubjectProperty) -> Any`

Get property value (async).

#### `async delete(prop: SubjectProperty) -> None`

Delete property (async).

#### `async flush() -> None`

Delete entire subject from storage (async).

#### `async get_ext_props() -> dict`

Get all extended properties (async).

#### `is_concurrency_safe() -> bool`

Whether storage supports concurrent access.

#### `is_persistent() -> bool`

Whether storage persists across restarts.

**See:** [Storage Backends](STORAGE_BACKENDS.md)

---

## Quick Links

- **Getting Started**
  - [README](../README.md) - Overview
  - [Quick Start](QUICKSTART.md) - 5-minute tutorial
  - [Core Concepts](CORE_CONCEPTS.md) - Framework fundamentals

- **Core Components**
  - [Subjects](SUBJECTS.md) - Reactive property store
  - [Event Handlers](EVENT_HANDLERS.md) - Event processing
  - [Middleware](MIDDLEWARE.md) - Cross-cutting concerns
  - [Container & DI](CONTAINER_DI.md) - Dependency injection

- **Advanced**
  - [Storage Backends](STORAGE_BACKENDS.md) - Persistence
  - [Integrations](INTEGRATIONS.md) - FastAPI, Pub/Sub, CloudEvents
  - [Testing](TESTING.md) - Testing strategies
  - [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
  - [Shell Mode](SHELL_MODE.md) - Interactive usage

- **Modules**
  - [krules_fastapi_env](../krules_fastapi_env/README.md) - FastAPI integration
  - [krules_cloudevents](../krules_cloudevents/README.md) - CloudEvents support
  - [krules_pubsub](../krules_pubsub/README.md) - Pub/Sub base
  - [krules_cloudevents_pubsub](../krules_cloudevents_pubsub/README.md) - Pub/Sub + CloudEvents
  - [redis_subjects_storage](../redis_subjects_storage/README.md) - Redis storage backend
