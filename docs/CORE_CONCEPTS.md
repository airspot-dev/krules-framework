# Core Concepts

Understanding the fundamental architecture of KRules Framework.

## Framework Philosophy

KRules is built on three core principles:

1. **Event-Driven Architecture** - Everything happens in response to events
2. **Reactive State Management** - State changes automatically trigger events
3. **Declarative Handlers** - Define what should happen, not how

## The Three Core Components

### 1. Subjects (Reactive State Store)

**Subjects** are dynamic entities with schema-less properties. When a property changes, the subject automatically emits a `subject-property-changed` event.

**Key characteristics:**
- **Schema-less** - No predefined structure, add properties dynamically
- **Reactive** - Property changes emit events automatically
- **Persistent** - Backed by storage (Redis, SQLite, in-memory)
- **Atomic** - Lambda values enable atomic operations

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()
device = container.subject("device-001")

# Set property → automatically emits subject-property-changed
await device.set("temperature", 75.5)

# Atomic increment
await device.set("reading_count", lambda c: c + 1)
```

### 2. Event Bus (Event Router)

**EventBus** routes events to matching handlers. Supports pattern matching, middleware, and error isolation.

**Key characteristics:**
- **Pattern matching** - Glob patterns (`device.*`), wildcards (`*`)
- **Async-first** - Built on asyncio for concurrent execution
- **Middleware** - Global event interception
- **Error isolation** - One handler error doesn't affect others

```python
container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Handler for specific event
@on("device.temperature_reading")
async def handle_reading(ctx):
    print(f"Temperature: {ctx.payload['value']}")

# Pattern matching
@on("device.*")  # Matches device.created, device.updated, etc.
async def log_device_event(ctx):
    print(f"Device event: {ctx.event_type}")

# Emit event
device = container.subject("device-001")
await emit("device.temperature_reading", device, {"value": 75.5})
```

### 3. Handlers (Event Processors)

**Handlers** are functions decorated with `@on` that react to events. Use `@when` to add conditional filters.

**Key characteristics:**
- **Declarative** - Define reactions, not control flow
- **Composable** - Stack filters with `@when`
- **Reusable** - Extract filters into functions
- **Async-friendly** - Native async/await support

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_high_temp(ctx):
    """Alert when temperature exceeds 80"""
    await ctx.emit("alert.high_temperature", {
        "device": ctx.subject.name,
        "temp": ctx.new_value
    })
```

## How Components Interact

Here's how the three components work together:

```
1. Property Change
   await device.set("temperature", 85)

2. Automatic Event Emission
   await EventBus.emit("subject-property-changed", device, {...})

3. Handler Matching
   EventBus finds handlers matching "subject-property-changed"

4. Filter Evaluation
   Check @when conditions (property_name == "temperature", new_value > 80)

5. Handler Execution
   alert_high_temp(ctx) runs

6. Event Cascade
   Handler emits "alert.high_temperature"
   → Process repeats for new event
```

### Example: Complete Flow

```python
from krules_core.container import KRulesContainer
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Step 1: Define handlers
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "status")
@when(lambda ctx: ctx.new_value == "error")
async def handle_error_status(ctx):
    """React to error status"""
    print(f"Device {ctx.subject.name} entered error state")
    await ctx.emit("alert.device_error", {
        "device_id": ctx.subject.name
    })

@on("alert.device_error")
async def send_alert(ctx):
    """Send alert notification"""
    device_id = ctx.payload["device_id"]
    print(f"ALERT: Device {device_id} error!")

# Step 2: Use subjects
device = container.subject("device-123")
await device.set("status", "ok")

# Step 3: Trigger event cascade
await device.set("status", "error")
# → Emits subject-property-changed (automatically)
# → handle_error_status matches & executes
# → Emits alert.device_error
# → send_alert matches & executes
```

## Event-Driven Paradigm

KRules follows a pure event-driven model where:

1. **State changes are events** - Setting a property emits an event
2. **Handlers react to events** - No direct calls between components
3. **Events cascade** - Handlers can emit new events
4. **Loose coupling** - Components don't know about each other

### Benefits

- **Scalability** - Add handlers without modifying existing code
- **Testability** - Test handlers in isolation
- **Maintainability** - Clear separation of concerns
- **Flexibility** - Change behavior by adding/removing handlers

### Event Cascade Pattern

Events can trigger other events, creating workflows:

```python
@on("order.created")
async def validate_order(ctx):
    order = ctx.subject
    if await order.get("total") > 0:
        await ctx.emit("payment.required")

@on("payment.required")
async def process_payment(ctx):
    # Process payment...
    await ctx.emit("payment.completed")

@on("payment.completed")
async def fulfill_order(ctx):
    await ctx.subject.set("status", "fulfilled")
    await ctx.emit("order.fulfilled")
```

**Execution flow:**
```
order.created
   ↓
payment.required
   ↓
payment.completed
   ↓
order.fulfilled
```

## Container (Dependency Injection)

The **KRulesContainer** manages dependencies using dependency injection.

**Why Container?**
- **Testability** - Easy to mock dependencies
- **Flexibility** - Swap implementations (storage, event bus)
- **Configuration** - Centralized setup

```python
from krules_core.container import KRulesContainer

# Create container
container = KRulesContainer()

# Get handlers (bound to container's event bus)
on, when, middleware, emit = container.handlers()

# Create subjects (bound to container's storage)
user = container.subject("user-123")
```

### Overriding Providers

Customize behavior by overriding providers:

```python
from dependency_injector import providers
from redis_subjects_storage.storage_impl import create_redis_storage

container = KRulesContainer()

# Override storage backend
from redis.asyncio import Redis
redis_client = await create_redis_client("redis://localhost:6379")
redis_factory = create_redis_storage(
    redis_client=redis_client,
    redis_prefix="app:"
)
container.subject_storage.override(providers.Object(redis_factory))

# Now all subjects use Redis
user = container.subject("user-123")
```

## When to Use KRules

KRules excels in scenarios requiring:

### ✅ Good Fit

- **IoT & Device Management** - React to sensor data, manage device state
- **Workflow Automation** - Multi-step processes with state transitions
- **Event Sourcing** - Track all state changes as events
- **Microservices** - Decouple services with event-driven communication
- **Real-time Systems** - Immediate reaction to state changes
- **Complex State Machines** - Manage entities through state transitions

### ❌ Not Ideal For

- **Simple CRUD apps** - Traditional frameworks may be simpler
- **Batch processing** - If events aren't the primary model
- **Pure REST APIs** - Without complex state management needs
- **Synchronous workflows** - If async complexity isn't needed

## Example Use Cases

### IoT Temperature Monitoring

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "temperature")
async def monitor_temperature(ctx):
    temp = ctx.new_value

    if temp > 90:
        await ctx.emit("alert.critical", {"temp": temp})
    elif temp > 80:
        await ctx.emit("alert.warning", {"temp": temp})

@on("alert.critical")
async def handle_critical(ctx):
    # Trigger cooling system
    device = ctx.subject
    await device.set("cooling_active", True)
```

### E-Commerce Order Processing

```python
@on("order.submitted")
async def validate_order(ctx):
    order = ctx.subject

    if await order.get("total") > 0 and await order.get("items_count") > 0:
        await order.set("status", "validated")
        await ctx.emit("payment.process")

@on("payment.process")
@when(async lambda ctx: await ctx.subject.get("status") == "validated")
async def process_payment(ctx):
    # Process payment...
    await ctx.subject.set("payment_status", "completed")
    await ctx.emit("order.ship")

@on("order.ship")
async def ship_order(ctx):
    await ctx.subject.set("status", "shipped")
    await ctx.emit("notification.order_shipped")
```

### User Account Management

```python
@on("user.registered")
async def setup_user(ctx):
    user = ctx.subject
    await user.set("status", "active")
    await user.set("created_at", datetime.now().isoformat())
    await ctx.emit("email.send_welcome")

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "email")
async def email_changed(ctx):
    # Trigger verification
    await ctx.emit("email.verify", {
        "new_email": ctx.new_value,
        "old_email": ctx.old_value
    })
```

## Design Patterns

### Reactive Property Pattern

Let property changes drive behavior:

```python
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "inventory")
@when(lambda ctx: ctx.new_value < 10)
async def low_inventory_alert(ctx):
    await ctx.emit("inventory.reorder", {
        "product": ctx.subject.name,
        "current": ctx.new_value
    })
```

### Event Cascade Pattern

Chain events for workflows:

```python
@on("step1.complete")
async def step2(ctx):
    # Do step 2...
    await ctx.emit("step2.complete")

@on("step2.complete")
async def step3(ctx):
    # Do step 3...
    await ctx.emit("workflow.complete")
```

### Guard Pattern

Use filters to prevent execution:

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

## Best Practices

1. **Use Container Always** - Never instantiate components directly
2. **Import Event Type Constants** - Use `SUBJECT_PROPERTY_CHANGED` from `event_types`
3. **Keep Handlers Focused** - One responsibility per handler
4. **Name Events Clearly** - Use `entity.action` pattern (e.g., `user.created`)
5. **Use Filters Liberally** - Prefer `@when` over `if` in handlers
6. **Avoid Infinite Loops** - Be careful with property changes in handlers
7. **Call await .store() Explicitly** - Properties aren't persisted until `await .store()`
8. **Await All Async Methods** - Subject methods (.set, .get, .store, etc.) and emit() require await

## What's Next?

- [Subjects](SUBJECTS.md) - Deep dive into reactive property store
- [Event Handlers](EVENT_HANDLERS.md) - Advanced handler patterns
- [Container & DI](CONTAINER_DI.md) - Dependency injection details
- [Storage Backends](STORAGE_BACKENDS.md) - Persistence options
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
