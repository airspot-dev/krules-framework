# Quick Start Guide

Get started with KRules in 5 minutes.

## Installation

```bash
pip install krules-framework
```

## Your First KRules Application

Create a file `app.py`:

```python
import asyncio
from datetime import datetime
from krules_core.container import KRulesContainer
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

# Initialize container
container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Define an event handler
@on("user.registered")
async def welcome_user(ctx):
    """Send welcome message to new users"""
    user = ctx.subject

    print(f"Welcome {await user.get('email')}!")

    # Set user properties
    await user.set("status", "active")
    await user.set("registration_date", datetime.now().isoformat())
    await user.set("login_count", 0)

    # Emit follow-up event
    await ctx.emit("email.send_welcome", {
        "to": await user.get("email"),
        "template": "welcome"
    })

# React to property changes
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "status")
async def log_status_change(ctx):
    """Log whenever user status changes"""
    print(f"User {ctx.subject.name}: {ctx.old_value} → {ctx.new_value}")

# Handle email sending
@on("email.send_welcome")
async def send_email(ctx):
    """Simulate email sending"""
    email = ctx.payload.get("to")
    print(f"Sending welcome email to {email}")

# Main execution
async def main():
    # Create a user subject
    user = container.subject("user-123")
    await user.set("email", "john@example.com")
    await user.set("name", "John Doe")

    # Emit registration event
    await emit("user.registered", user, {"ip": "192.168.1.1"})

    # Persist user to storage
    await user.store()

    print("\nUser data:", await user.dict())

if __name__ == "__main__":
    asyncio.run(main())
```

## Run It

```bash
python app.py
```

**Output:**
```
Welcome john@example.com!
User user-123: None → active
Sending welcome email to john@example.com

User data: {'name': 'user-123', 'email': 'john@example.com', 'name': 'John Doe',
            'status': 'active', 'registration_date': '2024-...', 'login_count': 0, 'ext': {}}
```

## What Just Happened?

1. **Container Setup** - Created `KRulesContainer` and got handler decorators
2. **Event Handlers** - Defined handlers with `@on` decorator
3. **Property Change Reaction** - Automatically reacted to `status` property change using `SUBJECT_PROPERTY_CHANGED`
4. **Event Cascade** - `user.registered` → `email.send_welcome` (event chaining)
5. **Subject State** - Stored user properties in the subject

## Key Concepts

### Container

The container manages all dependencies. Always start by creating a container:

```python
container = KRulesContainer()
on, when, middleware, emit = container.handlers()
```

### Subjects

Subjects are entities with dynamic properties:

```python
user = container.subject("user-123")
await user.set("email", "john@example.com")
email = await user.get("email")
```

### Event Handlers

Use `@on` decorator to handle events:

```python
@on("user.login")
async def handle_login(ctx):
    print(f"User {ctx.subject.name} logged in")
```

### Event Emission

Emit events from handlers or directly:

```python
# From handler
await ctx.emit("user.logged-in", {"timestamp": "..."})

# Direct emission
await emit("user.login", user, {"ip": "192.168.1.1"})
```

### Property Change Events

Subjects automatically emit `SUBJECT_PROPERTY_CHANGED` when properties change:

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name == "temperature")
async def monitor_temp(ctx):
    print(f"Temperature: {ctx.old_value} → {ctx.new_value}")
```

## Add Filters

Use `@when` to conditionally execute handlers:

```python
@on("payment.process")
@when(lambda ctx: ctx.payload.get("amount") > 0)
@when(lambda ctx: await ctx.subject.get("verified") == True)
async def process_payment(ctx):
    """Only process for verified users with amount > 0"""
    amount = ctx.payload.get("amount")
    print(f"Processing payment: ${amount}")
```

## Add Middleware

Middleware runs for all events:

```python
import time

@middleware
async def timing_middleware(ctx, next):
    """Log execution time for all handlers"""
    start = time.time()
    await next()
    duration = time.time() - start
    print(f"{ctx.event_type} took {duration:.3f}s")
```

## Use Redis Storage

By default, subjects are stored in memory. To use Redis:

```bash
pip install "krules-framework[redis]"
```

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

# Now subjects are persisted in Redis
user = container.subject("user-123")
await user.set("email", "john@example.com")
await user.store()  # Saves to Redis
```

## Testing Your Handlers

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.fixture
def container():
    return KRulesContainer()

@pytest.mark.asyncio
async def test_user_registration(container):
    on, when, middleware, emit = container.handlers()
    results = []

    @on("user.registered")
    async def handler(ctx):
        results.append("registered")
        await ctx.subject.set("status", "active")

    user = container.subject("test-user")
    await emit("user.registered", user)

    assert results == ["registered"]
    assert await user.get("status") == "active"
```

## What's Next?

- [Core Concepts](CORE_CONCEPTS.md) - Understand the framework architecture
- [Subjects](SUBJECTS.md) - Deep dive into reactive property store
- [Event Handlers](EVENT_HANDLERS.md) - Advanced handler patterns
- [Middleware](MIDDLEWARE.md) - Cross-cutting concerns
- [Storage Backends](STORAGE_BACKENDS.md) - Persistence options
- [Testing](TESTING.md) - Comprehensive testing strategies

## Common Patterns

### Event Cascade

Chain events to create workflows:

```python
@on("order.created")
async def create_order(ctx):
    await ctx.subject.set("status", "pending")
    await ctx.emit("order.validate")

@on("order.validate")
async def validate_order(ctx):
    if await ctx.subject.get("amount") > 0:
        await ctx.emit("payment.process")

@on("payment.process")
async def process_payment(ctx):
    # Process payment...
    await ctx.emit("order.confirmed")
```

### Lambda Values for Atomic Operations

Use lambda to update properties atomically:

```python
@on("user.login")
async def track_login(ctx):
    # Atomic increment
    await ctx.subject.set("login_count", lambda count: count + 1)

    # Atomic append to list
    await ctx.subject.set("login_history", lambda hist: hist + [datetime.now()])
```

### Reusable Filters

Define filters once, reuse everywhere:

```python
async def is_active(ctx):
    return await ctx.subject.get("status") == "active"

async def is_verified(ctx):
    return await ctx.subject.get("verified") == True

@on("user.action")
@when(is_active)
@when(is_verified)
async def handle_action(ctx):
    # Only for active, verified users
    pass
```

## Tips

1. **Always use Container** - Don't instantiate `Subject` or `EventBus` directly
2. **Use constants for event types** - Import from `krules_core.event_types`
3. **Await emit() in handlers** - Ensures event cascade completes
4. **Call .store() to persist** - Changes aren't saved until `.store()` is called
5. **Use @when for conditions** - Keep handler logic clean

## Troubleshooting

**Q: My handlers aren't being called**
- Make sure handlers are defined before emitting events
- Check event name matches exactly (case-sensitive)
- Verify filters aren't blocking execution

**Q: Properties aren't persisted**
- Call `subject.store()` to persist changes
- Check storage backend is configured correctly

**Q: Getting "RuntimeError: no running event loop"**
- Wrap execution in `asyncio.run(main())` or run within async context

## Ready to Build?

You now know the basics of KRules! Explore the detailed documentation to learn advanced patterns and production best practices.
