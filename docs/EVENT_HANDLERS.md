# Event Handlers

Event handlers are the core mechanism for reacting to events in KRules. They are defined using decorators and support pattern matching, conditional filters, and async execution.

## Handler Basics

### Defining Handlers

Get handler decorators from the container:

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()
```

**Never use decorators without container** - they must be bound to the container's event bus.

### The `@on` Decorator

Register handlers using `@on(*patterns)`:

```python
# Single event
@on("user.login")
async def handle_login(ctx):
    print(f"User {ctx.subject.name} logged in")

# Multiple events
@on("user.created", "user.updated", "user.deleted")
async def log_user_event(ctx):
    print(f"User event: {ctx.event_type}")

# Glob patterns
@on("device.*")  # Matches device.created, device.updated, etc.
async def handle_device(ctx):
    print(f"Device event: {ctx.event_type}")

# Wildcard (matches all events)
@on("*")
async def log_all(ctx):
    print(f"Event: {ctx.event_type}")
```

### Handler Function Signature

```python
async def handler(ctx: EventContext):
    # ctx.event_type - event name
    # ctx.subject - subject instance
    # ctx.payload - event data
    # ctx.emit() - emit new events
    pass
```

## EventContext

The `EventContext` object is passed to every handler:

### Core Attributes

```python
@on("user.action")
async def handler(ctx):
    # Event type
    event_type = ctx.event_type  # "user.action"

    # Subject
    subject = ctx.subject  # Subject instance

    # Event payload
    payload = ctx.payload  # dict with event data
```

### Property Change Attributes

For `subject-property-changed` events:

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
async def on_property_change(ctx):
    # Property name
    prop = ctx.property_name  # "email"

    # Old value
    old = ctx.old_value  # "old@example.com"

    # New value
    new = ctx.new_value  # "new@example.com"
```

### Methods

```python
@on("user.action")
async def handler(ctx):
    # Emit new event
    await ctx.emit("user.action_processed", {
        "result": "success"
    })

    # Custom metadata
    ctx.set_metadata("request_id", "12345")
    request_id = ctx.get_metadata("request_id")
```

## Event Patterns

### Exact Match

```python
@on("user.login")
async def handle_login(ctx):
    pass
```

Matches: `"user.login"`
Doesn't match: `"user.logout"`, `"admin.login"`

### Multiple Events

```python
@on("order.created", "order.updated", "order.deleted")
async def handle_order(ctx):
    if ctx.event_type == "order.created":
        # Handle creation
        pass
    elif ctx.event_type == "order.updated":
        # Handle update
        pass
```

### Glob Patterns

```python
# Matches: device.created, device.updated, device.deleted, device.xyz
@on("device.*")
async def handle_device(ctx):
    pass

# Matches: user.login.success, user.login.failed
@on("user.login.*")
async def handle_login_result(ctx):
    pass
```

### Wildcard

```python
# Matches ALL events
@on("*")
async def log_everything(ctx):
    print(f"{ctx.event_type} on {ctx.subject.name}")
```

**Use carefully** - wildcard handlers run for every event.

## Filters with `@when`

Add conditional execution using `@when` decorators:

### Single Filter

```python
@on("payment.process")
@when(lambda ctx: ctx.payload.get("amount") > 0)
async def process_payment(ctx):
    # Only runs if amount > 0
    pass
```

### Multiple Filters (AND Logic)

Stack `@when` decorators - **all must pass**:

```python
@on("admin.action")
@when(lambda ctx: ctx.payload.get("role") == "admin")
@when(lambda ctx: await ctx.subject.get("verified") == True)
@when(lambda ctx: not await ctx.subject.get("suspended", False))
async def admin_action(ctx):
    # Only for verified, non-suspended admins
    pass
```

### Reusable Filters

Extract filters into functions:

```python
async def is_active(ctx):
    return await ctx.subject.get("status") == "active"

async def is_premium(ctx):
    return await ctx.subject.get("tier") == "premium"

async def has_credits(ctx):
    return await ctx.subject.get("credits", 0) > 0

@on("feature.use")
@when(is_active)
@when(is_premium)
@when(has_credits)
async def use_premium_feature(ctx):
    await ctx.subject.set("credits", lambda c: c - 1)
```

### Async Filters

Filters can be async:

```python
async def check_external_api(ctx):
    # Call external API
    response = await http_client.get(f"/user/{ctx.subject.name}/status")
    return response.status == 200

@on("user.action")
@when(check_external_api)
async def handle_action(ctx):
    pass
```

### Property Change Filters

Common pattern for reacting to specific property changes:

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_high_temp(ctx):
    await ctx.emit("alert.high_temperature", {
        "device": ctx.subject.name,
        "temp": ctx.new_value
    })
```

## Decorator Order

**Decorator order doesn't matter** - KRules handles both patterns:

```python
# @when before @on
@when(is_active)
@on("user.action")
async def handler1(ctx):
    pass

# @on before @when
@on("user.action")
@when(is_active)
async def handler2(ctx):
    pass
```

Both work identically. Use whichever reads better.

## Handler Execution

### Async Handlers (Required)

**All handlers must be async in KRules 3.0. Sync handlers are no longer supported.**

```python
@on("user.action")
async def handler(ctx):
    # Can use await
    await ctx.emit("user.action_processed")

    # Async I/O
    async with httpx.AsyncClient() as client:
        await client.post("https://api.example.com/webhook")
```

### Execution Order

Handlers execute in **registration order**:

```python
@on("user.login")
async def first_handler(ctx):
    print("1")

@on("user.login")
async def second_handler(ctx):
    print("2")

# Emitting "user.login" prints: 1, 2
```

### Error Isolation

One handler's error doesn't affect others:

```python
@on("user.action")
async def handler1(ctx):
    raise Exception("Oops!")  # Error here...

@on("user.action")
async def handler2(ctx):
    print("Still runs!")  # ...doesn't prevent this
```

Errors are logged but don't stop event processing.

## Emitting Events

### From Handlers

Use `ctx.emit()`:

```python
@on("order.created")
async def process_order(ctx):
    order = ctx.subject
    await order.set("status", "processing")

    # Emit new event
    await ctx.emit("order.processing", {
        "order_id": order.name,
        "timestamp": datetime.now().isoformat()
    })
```

### Direct Emission

Use `emit()` function from container:

```python
container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Emit event
user = container.subject("user-123")
await emit("user.action", user, {"action": "login"})
```

### With Extra Metadata

Pass extra kwargs to `emit()`:

```python
# Extra metadata (available in ctx.get_metadata())
await ctx.emit("alert.critical", payload, topic="alerts", priority="high")

# Middleware can access metadata
@middleware
async def route_by_topic(ctx, next):
    topic = ctx.get_metadata("topic")
    if topic:
        print(f"Routing to topic: {topic}")
    await next()
```

## Common Patterns

### Property Change Reaction

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "status")
async def on_status_change(ctx):
    status = ctx.new_value

    if status == "error":
        await ctx.emit("alert.error", {
            "device": ctx.subject.name
        })
    elif status == "ok":
        await ctx.emit("alert.resolved", {
            "device": ctx.subject.name
        })
```

### Event Cascade

Chain events to create workflows:

```python
@on("order.submitted")
async def validate_order(ctx):
    if await ctx.subject.get("total") > 0:
        await ctx.emit("order.validated")

@on("order.validated")
async def process_payment(ctx):
    # Process payment...
    await ctx.emit("payment.completed")

@on("payment.completed")
async def ship_order(ctx):
    await ctx.subject.set("status", "shipped")
    await ctx.emit("order.shipped")
```

### Guard Pattern

Prevent execution based on conditions:

```python
def is_business_hours(ctx):
    hour = datetime.now().hour
    return 9 <= hour <= 17

@on("notification.send")
@when(is_business_hours)
async def send_notification(ctx):
    # Only send during business hours
    pass
```

### Aggregation Pattern

Collect data from multiple events:

```python
@on("sensor.reading")
async def aggregate_readings(ctx):
    device = ctx.subject
    reading = ctx.payload["value"]

    # Append to readings list
    await device.set("readings", lambda r: r + [reading])

    # If we have 10 readings, calculate average
    readings = await device.get("readings", default=[])
    if len(readings) >= 10:
        avg = sum(readings) / len(readings)
        await device.set("average", avg)
        await device.set("readings", [])  # Reset
        await ctx.emit("sensor.average_calculated", {"average": avg})
```

### State Machine Pattern

```python
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "status")
async def state_machine(ctx):
    state = ctx.new_value

    transitions = {
        "pending": "order.validate",
        "validated": "payment.process",
        "paid": "order.ship",
        "shipped": "order.complete"
    }

    if state in transitions:
        await ctx.emit(transitions[state])
```

### Retry Pattern

```python
@on("api.call")
@when(lambda ctx: await ctx.subject.get("retry_count", 0) < 3)
async def call_api_with_retry(ctx):
    try:
        # Call API
        response = await api_client.call()

        if response.ok:
            await ctx.subject.set("retry_count", 0)  # Reset
        else:
            raise Exception("API error")

    except Exception as e:
        # Increment retry count
        await ctx.subject.set("retry_count", lambda c: c + 1)

        # Retry after delay
        await asyncio.sleep(2 ** await ctx.subject.get("retry_count"))
        await ctx.emit("api.call")  # Retry
```

## Built-in Event Types

Use constants from `event_types` module:

```python
from krules_core.event_types import (
    SUBJECT_PROPERTY_CHANGED,
    SUBJECT_PROPERTY_DELETED,
    SUBJECT_DELETED
)

@on(SUBJECT_PROPERTY_CHANGED)
async def on_property_change(ctx):
    print(f"{ctx.property_name}: {ctx.old_value} → {ctx.new_value}")

@on(SUBJECT_PROPERTY_DELETED)
async def on_property_delete(ctx):
    print(f"Deleted property: {ctx.property_name}")

@on(SUBJECT_DELETED)
async def on_subject_delete(ctx):
    # ctx.payload contains final snapshot
    print(f"Subject deleted: {ctx.subject.name}")
    print(f"Final state: {ctx.payload}")
```

## Best Practices

1. **Use constants** - Import from `event_types` for built-in events
2. **Name events clearly** - Use `entity.action` pattern (`user.created`, `order.shipped`)
3. **Keep handlers focused** - One responsibility per handler
4. **Prefer @when over if** - Use filters for conditional execution
5. **Extract reusable filters** - Share filter logic across handlers
6. **Await ctx.emit()** - Ensures event cascade completes
7. **Handle errors gracefully** - Don't let errors crash handlers
8. **Avoid infinite loops** - Be careful with property changes in handlers
9. **Use glob patterns** - Simplify multiple related events
10. **Document complex filters** - Explain non-obvious conditions

## Anti-Patterns

### ❌ Don't: Create infinite loops

```python
@on(SUBJECT_PROPERTY_CHANGED)
async def bad_handler(ctx):
    # Infinite loop! Each set triggers this handler
    await ctx.subject.set("counter", lambda c: c + 1)
```

✅ **Do: Mute or use filters**

```python
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name != "counter")  # Guard
async def good_handler(ctx):
    await ctx.subject.set("counter", lambda c: c + 1, muted=True)
```

### ❌ Don't: Use if when @when is clearer

```python
@on("user.action")
async def bad_handler(ctx):
    if await ctx.subject.get("status") == "active":
        # Do something
        pass
```

✅ **Do: Use @when decorator**

```python
@on("user.action")
@when(lambda ctx: await ctx.subject.get("status") == "active")
async def good_handler(ctx):
    # Do something
    pass
```

### ❌ Don't: Forget to await emit()

```python
@on("user.action")
async def bad_handler(ctx):
    ctx.emit("follow_up")  # Not awaited - cascade may not complete
```

✅ **Do: Always await**

```python
@on("user.action")
async def good_handler(ctx):
    await ctx.emit("follow_up")  # Awaited
```

### ❌ Don't: Use wildcard carelessly

```python
@on("*")
async def bad_handler(ctx):
    # Runs for EVERY event - performance impact
    await expensive_operation()
```

✅ **Do: Use specific patterns**

```python
@on("user.*")  # Only user events
async def good_handler(ctx):
    await expensive_operation()
```

## Testing Handlers

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.fixture
def container():
    return KRulesContainer()

@pytest.mark.asyncio
async def test_handler(container):
    on, when, middleware, emit = container.handlers()
    results = []

    @on("user.action")
    @when(lambda ctx: ctx.payload.get("valid") == True)
    async def handler(ctx):
        results.append(ctx.event_type)

    user = container.subject("test-user")

    # Test with valid payload
    await emit("user.action", user, {"valid": True})
    assert results == ["user.action"]

    # Test with invalid payload (filter blocks)
    await emit("user.action", user, {"valid": False})
    assert results == ["user.action"]  # Still just one
```

## What's Next?

- [Middleware](MIDDLEWARE.md) - Cross-cutting concerns
- [Container & DI](CONTAINER_DI.md) - Dependency injection
- [Testing](TESTING.md) - Testing strategies
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [API Reference](API_REFERENCE.md) - Complete API
