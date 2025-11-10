# Subjects - Reactive Property Store

Subjects are the core state management mechanism in KRules. They are dynamic entities with schema-less properties that automatically emit events when state changes.

## What is a Subject?

A **Subject** is:
- A named entity (`"user-123"`, `"device-456"`)
- With dynamic properties (no predefined schema)
- That automatically emits events on changes
- Backed by persistent storage (Redis, SQLite, in-memory)
- Supporting atomic operations via lambda values

Think of subjects as reactive dictionaries with event emission and persistence.

## Creating Subjects

Always create subjects through the container:

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()

# Create or retrieve subject
user = container.subject("user-123")
device = container.subject("device-456")
order = container.subject("order-789")
```

**Subject names** are strings that uniquely identify the entity. Choose meaningful, consistent naming:
- `"user-{id}"` - User accounts
- `"device-{serial}"` - IoT devices
- `"order-{order_id}"` - Orders
- `"session-{uuid}"` - Sessions

## Working with Properties

### Setting Properties

Set properties using `await .set()`:

```python
user = container.subject("user-123")

# Simple values
await user.set("name", "John Doe")
await user.set("email", "john@example.com")
await user.set("age", 30)

# Complex values
await user.set("address", {
    "street": "123 Main St",
    "city": "Boston",
    "zip": "02101"
})

await user.set("tags", ["premium", "verified"])
```

**Every `.set()` emits a `subject-property-changed` event** (unless muted).
**All Subject methods are async in KRules 3.0** - always use `await`.

### Getting Properties

Retrieve properties using `await .get()`:

```python
name = await user.get("name")  # "John Doe"
age = await user.get("age")    # 30

# With default value
status = await user.get("status", default="inactive")  # Returns "inactive" if not set

# Raises AttributeError if property doesn't exist and no default
try:
    missing = await user.get("missing_property")
except AttributeError:
    print("Property doesn't exist")
```

### Lambda Values (Atomic Operations)

Use lambda functions for atomic updates based on current value:

```python
user = container.subject("user-123")

# Atomic increment
await user.set("login_count", 0)
await user.set("login_count", lambda count: count + 1)  # count is current value

# Atomic append to list
await user.set("login_history", [])
await user.set("login_history", lambda hist: hist + [datetime.now()])

# Conditional update
await user.set("max_score", lambda current: max(current, new_score))
```

**Lambda signature:**
```python
lambda current_value: new_value
```

The lambda receives the current property value and must return the new value.

### Deleting Properties

Remove properties using `.delete()`:

```python
await user.set("temp_token", "abc123")
await user.delete("temp_token")  # Property removed

# Check existence first
if await user.has("temp_token"):
    await user.delete("temp_token")
```

Deleting a property emits `subject-property-deleted` event.

### Checking Existence

Use `await .has()` to check if property exists:

```python
if await user.has("email"):
    print(f"Email: {await user.get('email')}")

if not await user.has("admin"):
    await user.set("admin", False)
```

### Iterating Properties

Iterate over property names:

```python
await user.set("name", "John")
await user.set("email", "john@example.com")
await user.set("age", 30)

# Iterate over property names
for prop_name in await user.keys():
    value = await user.get(prop_name)
    print(f"{prop_name}: {value}")

# Get property count
keys = await user.keys()
count = len(keys)  # 3
```

## Property Types

Subjects support two property types:

### Default Properties (Reactive)

Standard properties that emit `subject-property-changed` events:

```python
await user.set("email", "john@example.com")  # Emits event
```

### Extended Properties (Metadata)

Extended properties store metadata without emitting events:

```python
# Set extended property (no event emission)
await user.set_ext("last_ip", "192.168.1.1")
await user.set_ext("user_agent", "Mozilla/5.0...")

# Get extended property
ip = await user.get_ext("last_ip")
```

**Use extended properties for:**
- Metadata that shouldn't trigger reactions
- Internal tracking (IP addresses, user agents)
- Cache data
- Debugging information

## Property Change Events

Every property change (via `.set()`) automatically emits a `subject-property-changed` event.

**Event payload:**
```python
{
    "property_name": "email",
    "value": "new@example.com",      # new value
    "old_value": "old@example.com"   # previous value
}
```

**React to property changes:**

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "email")
async def on_email_change(ctx):
    print(f"Email changed: {ctx.old_value} → {ctx.new_value}")
    await ctx.emit("email.verification_required", {
        "new_email": ctx.new_value
    })
```

**EventContext attributes for property changes:**
- `ctx.property_name` - Name of changed property
- `ctx.old_value` - Previous value (None if new property)
- `ctx.new_value` - New value
- `ctx.subject` - The subject
- `ctx.extra` - Extra context dict (see below)

### Passing Extra Context

You can pass additional context to event handlers using the `extra` parameter:

```python
# Set with extra context
await user.set("status", "suspended", extra={
    "reason": "policy_violation",
    "admin_id": "admin-123",
    "timestamp": datetime.now().isoformat()
})

# Delete with extra context
await user.delete("temp_data", extra={
    "reason": "expired",
    "retention_days": 30
})

# Access extra in handler
@on(SUBJECT_PROPERTY_CHANGED)
async def on_status_change(ctx):
    if ctx.property_name == "status" and ctx.new_value == "suspended":
        # Access extra context
        reason = ctx.extra.get("reason") if ctx.extra else None
        admin_id = ctx.extra.get("admin_id") if ctx.extra else None

        await ctx.emit("user.suspended", {
            "reason": reason,
            "admin": admin_id
        })
```

**Use `extra` for:**
- Audit trail information (who made the change, when, why)
- Business context (approval workflow, user actions)
- Debugging metadata (source system, request ID)
- Conditional handler logic

**Important:** The `extra` dict is optional and may be `None` - always check before accessing:

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def handler(ctx):
    # Safe access
    reason = ctx.extra.get("reason") if ctx.extra else "unknown"

    # Or with default
    user_id = (ctx.extra or {}).get("user_id", "system")
```

### Muted Properties (No Events)

Prevent event emission using `muted=True`:

```python
# Set without emitting event
await user.set("internal_counter", 0, muted=True)
await user.set("internal_counter", lambda c: c + 1, muted=True)
```

**Use muted properties when:**
- Updating frequently (avoid event storm)
- Internal bookkeeping
- Within handlers to prevent infinite loops

## Caching & Performance

Subjects use an intelligent caching system to optimize performance. You can control caching behavior at both the Subject level and per-operation level.

### Cache Strategy

By default, Subject operations use caching for performance:

```python
# Default: caching enabled
user = container.subject("user-123")
await user.set("name", "John")    # Cached
await user.set("email", "j@e.com") # Cached
await user.store()                 # Persist all changes to storage
```

**Caching behavior:**
- **Enabled (default)** - Changes cached in memory, written on `.store()`
- **Disabled** - Each operation immediately hits storage
- **Trade-off** - Cache = performance, No cache = consistency

### Per-Operation Cache Control

Use the `use_cache` parameter to control caching for specific operations:

```python
user = container.subject("user-123")

# Write immediately to storage (bypass cache)
await user.set("counter", 1, use_cache=False)

# Read fresh value from storage (bypass cache)
fresh_value = await user.get("counter", use_cache=False)

# Delete immediately from storage
await user.delete("temp_field", use_cache=False)
```

**When to use `use_cache=False`:**
- **Cross-process coordination** - Multiple processes/containers accessing same subject
- **Atomic operations** - Lambda values with `use_cache=False` ensure atomic storage updates
- **Fresh data required** - Reading latest value modified by another process
- **Immediate persistence** - Critical data that must survive crashes

**Example - Distributed counter:**
```python
# Multiple processes can safely increment the same counter
counter = container.subject("global-counter")

# Atomic increment directly in storage (safe across processes)
await counter.set("count", lambda c: (c or 0) + 1, use_cache=False)

# Read fresh value from storage
current = await counter.get("count", use_cache=False)
```

### Subject-Level Cache Control

Configure default caching behavior when creating a Subject:

```python
from krules_core.subject.storaged_subject import Subject

# Create subject with caching disabled by default
subject = Subject(
    name="realtime-metrics",
    storage=storage_factory,
    event_bus=event_bus,
    use_cache_default=False
)

# All operations default to use_cache=False
await subject.set("metric", 100)  # Writes immediately to storage

# Can override per-operation
await subject.set("temp", "value", use_cache=True)  # Use cache for this one
```

**When to disable caching by default:**
- Real-time metrics and telemetry
- Subjects accessed by multiple processes
- Low-frequency operations where caching overhead isn't worth it
- Debugging scenarios requiring immediate persistence

### Cache Synchronization

When using `use_cache=False` on a Subject that has an active cache, the cache is automatically synchronized:

```python
user = container.subject("user-123")

# Load cache
await user.set("status", "active")

# Direct storage write also updates cache
await user.set("status", "inactive", use_cache=False)

# Cache is synchronized - returns "inactive"
cached_value = await user.get("status", use_cache=True)
```

This ensures consistency between cache and storage.

### Batch Operations

Use caching for batch operations:

```python
user = container.subject("user-123")

# Multiple changes cached
await user.set("name", "John")
await user.set("email", "john@example.com")
await user.set("age", 30)
await user.set("status", "active")

# Persist all at once
await user.store()
```

### When to Call `.store()`

```python
# ✅ Good: Batch changes
await user.set("field1", "value1")
await user.set("field2", "value2")
await user.store()  # Persist together

# ❌ Inefficient: Store after each change
await user.set("field1", "value1")
await user.store()
await user.set("field2", "value2")
await user.store()

# ✅ Good: Disable cache for hot paths
await user.set("counter", lambda c: c + 1, use_cache=False)  # Direct write
```

## Advanced Operations

### Export to Dictionary

Convert subject to dict:

```python
await user.set("name", "John")
await user.set("email", "john@example.com")
await user.set_ext("last_login", "2024-01-01")

data = await user.dict()
# {
#     "name": "user-123",
#     "name": "John",
#     "email": "john@example.com",
#     "ext": {
#         "last_login": "2024-01-01"
#     }
# }
```

### Flush (Delete Subject)

Delete entire subject from storage:

```python
user = container.subject("user-123")
await user.flush()  # Deletes subject entirely
```

**What `.flush()` does:**
1. Emits `subject-property-deleted` for each property
2. Emits `subject-deleted` event with final snapshot
3. Deletes subject from storage
4. Resets cache

**Event payload for `subject-deleted`:**
```python
{
    "props": {
        "name": "John",
        "email": "john@example.com"
    },
    "ext_props": {
        "last_login": "2024-01-01"
    }
}
```

## Subject Lifecycle

```python
# 1. Create/retrieve subject
user = container.subject("user-123")

# 2. Load from storage (automatic on first access)
name = await user.get("name")  # Loads from storage if not cached

# 3. Modify properties
await user.set("email", "new@example.com")  # Cached
await user.set("login_count", lambda c: c + 1)  # Cached

# 4. Persist changes
await user.store()  # Write to storage

# 5. Delete subject (optional)
await user.flush()  # Remove from storage
```

## Common Patterns

### Counter Pattern

```python
# Initialize
await user.set("page_views", 0)

# Increment atomically
@on("page.view")
async def track_view(ctx):
    await ctx.subject.set("page_views", lambda c: c + 1)
```

### State Machine Pattern

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "status")
async def on_status_change(ctx):
    status = ctx.new_value

    if status == "pending":
        await ctx.emit("order.validate")
    elif status == "validated":
        await ctx.emit("payment.process")
    elif status == "paid":
        await ctx.emit("order.ship")
```

### Audit Trail Pattern

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def audit_changes(ctx):
    audit = container.subject(f"audit-{ctx.subject.name}")
    await audit.set("changes", lambda hist: hist + [{
        "property": ctx.property_name,
        "old": ctx.old_value,
        "new": ctx.new_value,
        "timestamp": datetime.now().isoformat()
    }])
    await audit.store()
```

### Derived Property Pattern

```python
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name in ["first_name", "last_name"])
async def update_full_name(ctx):
    user = ctx.subject
    full_name = f"{await user.get('first_name', '')} {await user.get('last_name', '')}".strip()
    await user.set("full_name", full_name, muted=True)  # Muted to avoid loop
```

## Best Practices

1. **Meaningful names** - Use consistent naming conventions
2. **Call .store()** - Changes aren't persisted until explicit `.store()`
3. **Use lambdas for atomicity** - `lambda c: c + 1` is atomic
4. **Mute when appropriate** - Prevent event storms with `muted=True`
5. **Extended for metadata** - Use `.set_ext()` for non-reactive data
6. **Batch updates** - Group `.set()` calls, single `.store()`
7. **Check existence** - Use `await subject.has("prop")` before `.get()`
8. **Default values** - Always provide defaults: `.get("prop", default=0)`

## Anti-Patterns

### ❌ Don't: Set in handler without muting

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def bad_handler(ctx):
    # Infinite loop! Each set() triggers this handler again
    await ctx.subject.set("counter", lambda c: c + 1)
```

✅ **Do: Mute or use extended property**

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def good_handler(ctx):
    await ctx.subject.set("counter", lambda c: c + 1, muted=True)
```

### ❌ Don't: Forget .store()

```python
await user.set("email", "john@example.com")
# Email not persisted!
```

✅ **Do: Call .store()**

```python
await user.set("email", "john@example.com")
await user.store()  # Persisted
```

### ❌ Don't: Use .set() in loops without batching

```python
for i in range(1000):
    await user.set(f"field_{i}", i, use_cache=False)  # 1000 writes!
```

✅ **Do: Batch with caching**

```python
for i in range(1000):
    await user.set(f"field_{i}", i)  # Cached
await user.store()  # Single write
```

## What's Next?

- [Event Handlers](EVENT_HANDLERS.md) - React to property changes
- [Storage Backends](STORAGE_BACKENDS.md) - Persistence options
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [API Reference](API_REFERENCE.md) - Complete Subject API
