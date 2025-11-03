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

Set properties using `.set()`:

```python
user = container.subject("user-123")

# Simple values
user.set("name", "John Doe")
user.set("email", "john@example.com")
user.set("age", 30)

# Complex values
user.set("address", {
    "street": "123 Main St",
    "city": "Boston",
    "zip": "02101"
})

user.set("tags", ["premium", "verified"])
```

**Every `.set()` emits a `subject-property-changed` event** (unless muted).

### Getting Properties

Retrieve properties using `.get()`:

```python
name = user.get("name")  # "John Doe"
age = user.get("age")    # 30

# With default value
status = user.get("status", default="inactive")  # Returns "inactive" if not set

# Raises AttributeError if property doesn't exist and no default
try:
    missing = user.get("missing_property")
except AttributeError:
    print("Property doesn't exist")
```

### Lambda Values (Atomic Operations)

Use lambda functions for atomic updates based on current value:

```python
user = container.subject("user-123")

# Atomic increment
user.set("login_count", 0)
user.set("login_count", lambda count: count + 1)  # count is current value

# Atomic append to list
user.set("login_history", [])
user.set("login_history", lambda hist: hist + [datetime.now()])

# Conditional update
user.set("max_score", lambda current: max(current, new_score))
```

**Lambda signature:**
```python
lambda current_value: new_value
```

The lambda receives the current property value and must return the new value.

### Deleting Properties

Remove properties using `.delete()`:

```python
user.set("temp_token", "abc123")
user.delete("temp_token")  # Property removed

# Check existence first
if "temp_token" in user:
    user.delete("temp_token")
```

Deleting a property emits `subject-property-deleted` event.

### Checking Existence

Use `in` operator to check if property exists:

```python
if "email" in user:
    print(f"Email: {user.get('email')}")

if "admin" not in user:
    user.set("admin", False)
```

### Iterating Properties

Iterate over property names:

```python
user.set("name", "John")
user.set("email", "john@example.com")
user.set("age", 30)

# Iterate over property names
for prop_name in user:
    value = user.get(prop_name)
    print(f"{prop_name}: {value}")

# Get property count
count = len(user)  # 3
```

## Property Types

Subjects support two property types:

### Default Properties (Reactive)

Standard properties that emit `subject-property-changed` events:

```python
user.set("email", "john@example.com")  # Emits event
```

### Extended Properties (Metadata)

Extended properties store metadata without emitting events:

```python
# Set extended property (no event emission)
user.set_ext("last_ip", "192.168.1.1")
user.set_ext("user_agent", "Mozilla/5.0...")

# Get extended property
ip = user.get_ext("last_ip")
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

### Muted Properties (No Events)

Prevent event emission using `muted=True`:

```python
# Set without emitting event
user.set("internal_counter", 0, muted=True)
user.set("internal_counter", lambda c: c + 1, muted=True)
```

**Use muted properties when:**
- Updating frequently (avoid event storm)
- Internal bookkeeping
- Within handlers to prevent infinite loops

## Caching & Performance

Subjects use an intelligent caching system to optimize performance.

### Cache Strategy

```python
# Default: caching enabled
user = container.subject("user-123")
user.set("name", "John")    # Cached
user.set("email", "j@e.com") # Cached
user.store()                 # Persist all changes

# Disable caching for single operation
user.set("counter", 1, use_cache=False)  # Immediate write to storage
```

**Caching behavior:**
- **Enabled (default)** - Changes cached in memory, written on `.store()`
- **Disabled** - Each operation immediately hits storage
- **Trade-off** - Cache = performance, No cache = consistency

### Batch Operations

Use caching for batch operations:

```python
user = container.subject("user-123")

# Multiple changes cached
user.set("name", "John")
user.set("email", "john@example.com")
user.set("age", 30)
user.set("status", "active")

# Persist all at once
user.store()
```

### When to Call `.store()`

```python
# ✅ Good: Batch changes
user.set("field1", "value1")
user.set("field2", "value2")
user.store()  # Persist together

# ❌ Inefficient: Store after each change
user.set("field1", "value1")
user.store()
user.set("field2", "value2")
user.store()

# ✅ Good: Disable cache for hot paths
user.set("counter", lambda c: c + 1, use_cache=False)  # Direct write
```

## Advanced Operations

### Export to Dictionary

Convert subject to dict:

```python
user.set("name", "John")
user.set("email", "john@example.com")
user.set_ext("last_login", "2024-01-01")

data = user.dict()
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
user.flush()  # Deletes subject entirely
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

## AwaitableResult Pattern

Subject operations return `AwaitableResult`, supporting both sync and async contexts.

### Sync Context

```python
# Use without await
user.set("email", "john@example.com")
value = user.get("email")
```

### Async Context

```python
# Await to ensure event handlers complete
await user.set("email", "john@example.com")

# Get return values
new_val, old_val = await user.set("counter", lambda c: c + 1)
print(f"Incremented from {old_val} to {new_val}")
```

**When to await:**
- In async handlers when order matters
- When you need to ensure events complete
- To get return values (new_value, old_value)

**When sync is fine:**
- Fire-and-forget property updates
- Event order doesn't matter
- Not in async context

## Subject Lifecycle

```python
# 1. Create/retrieve subject
user = container.subject("user-123")

# 2. Load from storage (automatic on first access)
name = user.get("name")  # Loads from storage if not cached

# 3. Modify properties
user.set("email", "new@example.com")  # Cached
user.set("login_count", lambda c: c + 1)  # Cached

# 4. Persist changes
user.store()  # Write to storage

# 5. Delete subject (optional)
user.flush()  # Remove from storage
```

## Common Patterns

### Counter Pattern

```python
# Initialize
user.set("page_views", 0)

# Increment atomically
@on("page.view")
async def track_view(ctx):
    ctx.subject.set("page_views", lambda c: c + 1)
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
    audit.set("changes", lambda hist: hist + [{
        "property": ctx.property_name,
        "old": ctx.old_value,
        "new": ctx.new_value,
        "timestamp": datetime.now().isoformat()
    }])
    audit.store()
```

### Derived Property Pattern

```python
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name in ["first_name", "last_name"])
async def update_full_name(ctx):
    user = ctx.subject
    full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
    user.set("full_name", full_name, muted=True)  # Muted to avoid loop
```

## Best Practices

1. **Meaningful names** - Use consistent naming conventions
2. **Call .store()** - Changes aren't persisted until explicit `.store()`
3. **Use lambdas for atomicity** - `lambda c: c + 1` is atomic
4. **Mute when appropriate** - Prevent event storms with `muted=True`
5. **Extended for metadata** - Use `.set_ext()` for non-reactive data
6. **Batch updates** - Group `.set()` calls, single `.store()`
7. **Check existence** - Use `if "prop" in subject` before `.get()`
8. **Default values** - Always provide defaults: `.get("prop", default=0)`

## Anti-Patterns

### ❌ Don't: Set in handler without muting

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def bad_handler(ctx):
    # Infinite loop! Each set() triggers this handler again
    ctx.subject.set("counter", lambda c: c + 1)
```

✅ **Do: Mute or use extended property**

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def good_handler(ctx):
    ctx.subject.set("counter", lambda c: c + 1, muted=True)
```

### ❌ Don't: Forget .store()

```python
user.set("email", "john@example.com")
# Email not persisted!
```

✅ **Do: Call .store()**

```python
user.set("email", "john@example.com")
user.store()  # Persisted
```

### ❌ Don't: Use .set() in loops without batching

```python
for i in range(1000):
    user.set(f"field_{i}", i, use_cache=False)  # 1000 writes!
```

✅ **Do: Batch with caching**

```python
for i in range(1000):
    user.set(f"field_{i}", i)  # Cached
user.store()  # Single write
```

## What's Next?

- [Event Handlers](EVENT_HANDLERS.md) - React to property changes
- [Storage Backends](STORAGE_BACKENDS.md) - Persistence options
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [API Reference](API_REFERENCE.md) - Complete Subject API
