# Middleware

Middleware provides a mechanism for intercepting and processing all events globally. It's ideal for cross-cutting concerns like logging, timing, authentication, and error handling.

## What is Middleware?

**Middleware** is a function that:
- Runs for every event
- Can inspect/modify the event context
- Controls whether handler execution continues
- Follows the chain of responsibility pattern

Think of middleware as a pipeline that every event flows through before reaching handlers.

## Defining Middleware

Get the middleware decorator from the container:

```python
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

@middleware
async def my_middleware(ctx, next):
    """Run logic before and after handlers"""
    print(f"Before: {ctx.event_type}")
    await next()  # Call next middleware/handler
    print(f"After: {ctx.event_type}")
```

## Middleware Signature

```python
async def middleware_function(ctx: EventContext, next: Callable):
    # ctx - EventContext (same as handlers)
    # next - Callable to invoke next middleware/handler

    # Logic before handlers
    await next()  # Execute next middleware/handlers
    # Logic after handlers
```

**Important:** Always call `await next()` unless intentionally short-circuiting.

## Middleware Chain

Multiple middleware form a chain:

```python
@middleware
async def first(ctx, next):
    print("1: before")
    await next()
    print("1: after")

@middleware
async def second(ctx, next):
    print("2: before")
    await next()
    print("2: after")

@on("test.event")
async def handler(ctx):
    print("Handler")
```

**Execution order:**
```
1: before
2: before
Handler
2: after
1: after
```

Middleware executes in reverse **registration order** (like an onion).

## Common Use Cases

### Logging Middleware

Log all events:

```python
import logging

logger = logging.getLogger(__name__)

@middleware
async def logging_middleware(ctx, next):
    """Log every event"""
    logger.info(f"Event: {ctx.event_type} on {ctx.subject.name}")
    await next()
```

### Timing Middleware

Measure handler execution time:

```python
import time

@middleware
async def timing_middleware(ctx, next):
    """Track execution time"""
    start = time.time()
    await next()
    duration = time.time() - start
    print(f"{ctx.event_type} took {duration:.3f}s")
```

### Error Handling Middleware

Catch and handle errors globally:

```python
@middleware
async def error_handling_middleware(ctx, next):
    """Global error handler"""
    try:
        await next()
    except Exception as e:
        logger.error(f"Handler error in {ctx.event_type}: {e}", exc_info=True)

        # Emit error event
        await ctx.emit("error.handler_failed", {
            "original_event": ctx.event_type,
            "error": str(e),
            "subject": ctx.subject.name
        })
```

### Authentication Middleware

Validate authentication:

```python
@middleware
async def auth_middleware(ctx, next):
    """Check authentication"""
    token = ctx.payload.get("auth_token")

    if not token:
        logger.warning(f"Unauthenticated event: {ctx.event_type}")
        return  # Short-circuit - don't call next()

    # Validate token
    if not validate_token(token):
        logger.warning(f"Invalid token for: {ctx.event_type}")
        return

    await next()  # Proceed if authenticated
```

### Request Context Middleware

Inject request-specific context:

```python
@middleware
async def request_context_middleware(ctx, next):
    """Add request context to all handlers"""
    request_id = ctx.payload.get("request_id", str(uuid.uuid4()))

    # Store in metadata
    ctx.set_metadata("request_id", request_id)

    await next()
```

### Metrics Middleware

Collect metrics:

```python
@middleware
async def metrics_middleware(ctx, next):
    """Track event metrics"""
    start = time.time()

    try:
        await next()
        # Success metric
        metrics.increment(f"event.{ctx.event_type}.success")
    except Exception as e:
        # Error metric
        metrics.increment(f"event.{ctx.event_type}.error")
        raise
    finally:
        # Timing metric
        duration = time.time() - start
        metrics.timing(f"event.{ctx.event_type}.duration", duration)
```

## Short-Circuiting

Prevent handler execution by not calling `next()`:

```python
@middleware
async def rate_limit_middleware(ctx, next):
    """Rate limit events"""
    subject = ctx.subject
    last_event = subject.get_ext("last_event_time", default=0)

    # Check rate limit (max 1 event per second)
    now = time.time()
    if now - last_event < 1.0:
        logger.warning(f"Rate limit exceeded for {subject.name}")
        return  # Short-circuit - don't call next()

    # Update last event time
    subject.set_ext("last_event_time", now)

    await next()
```

## Accessing Metadata

Use metadata to pass data between middleware:

```python
@middleware
async def add_context(ctx, next):
    """Add context"""
    ctx.set_metadata("user_id", "123")
    ctx.set_metadata("tenant", "acme")
    await next()

@middleware
async def use_context(ctx, next):
    """Use context from previous middleware"""
    user_id = ctx.get_metadata("user_id")
    tenant = ctx.get_metadata("tenant")

    print(f"Processing for user {user_id} in tenant {tenant}")
    await next()
```

## Conditional Middleware

Apply middleware logic conditionally:

```python
@middleware
async def conditional_middleware(ctx, next):
    """Only log certain events"""
    if ctx.event_type.startswith("admin."):
        logger.info(f"Admin event: {ctx.event_type}")

    await next()
```

## Middleware Patterns

### Decorator Pattern

Wrap handlers with additional behavior:

```python
@middleware
async def transaction_middleware(ctx, next):
    """Wrap in database transaction"""
    async with db.transaction():
        await next()
```

### Observer Pattern

Notify external systems:

```python
@middleware
async def webhook_middleware(ctx, next):
    """Send webhook for all events"""
    await next()  # Execute handlers first

    # Then notify webhook
    await webhook_client.notify({
        "event": ctx.event_type,
        "subject": ctx.subject.name,
        "timestamp": datetime.now().isoformat()
    })
```

### Circuit Breaker Pattern

Protect against cascading failures:

```python
from collections import defaultdict

error_counts = defaultdict(int)

@middleware
async def circuit_breaker_middleware(ctx, next):
    """Circuit breaker for failing subjects"""
    subject_key = ctx.subject.name

    # Check if circuit is open
    if error_counts[subject_key] > 5:
        logger.warning(f"Circuit open for {subject_key}")
        return  # Short-circuit

    try:
        await next()
        # Reset on success
        error_counts[subject_key] = 0
    except Exception as e:
        # Increment error count
        error_counts[subject_key] += 1
        raise
```

## Multiple Middleware

Combine multiple middleware for layered functionality:

```python
@middleware
async def logging_mw(ctx, next):
    logger.info(f"Event: {ctx.event_type}")
    await next()

@middleware
async def timing_mw(ctx, next):
    start = time.time()
    await next()
    print(f"Took: {time.time() - start:.3f}s")

@middleware
async def error_mw(ctx, next):
    try:
        await next()
    except Exception as e:
        logger.error(f"Error: {e}")
        raise

# Execution order: error_mw → timing_mw → logging_mw → handlers
```

## Testing Middleware

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.mark.asyncio
async def test_middleware():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    results = []

    @middleware
    async def test_mw(ctx, next):
        results.append("before")
        await next()
        results.append("after")

    @on("test.event")
    async def handler(ctx):
        results.append("handler")

    user = container.subject("test")
    await emit("test.event", user)

    assert results == ["before", "handler", "after"]
```

## Best Practices

1. **Always call next()** - Unless intentionally short-circuiting
2. **Keep middleware fast** - Runs for every event
3. **Use metadata** - Pass data between middleware and handlers
4. **Handle errors** - Don't let middleware crash silently
5. **Order matters** - Register middleware in logical order
6. **Document behavior** - Explain what middleware does
7. **Test thoroughly** - Middleware affects all handlers

## Anti-Patterns

### ❌ Don't: Forget to call next()

```python
@middleware
async def bad_middleware(ctx, next):
    print("Before")
    # Forgot to call next() - handlers never run!
    print("After")
```

✅ **Do: Always call next()**

```python
@middleware
async def good_middleware(ctx, next):
    print("Before")
    await next()
    print("After")
```

### ❌ Don't: Do expensive operations

```python
@middleware
async def bad_middleware(ctx, next):
    # Expensive operation for EVERY event
    await slow_external_api_call()
    await next()
```

✅ **Do: Keep middleware fast**

```python
@middleware
async def good_middleware(ctx, next):
    # Quick check, only call API if needed
    if ctx.event_type.startswith("admin."):
        await external_api_call()
    await next()
```

### ❌ Don't: Swallow errors silently

```python
@middleware
async def bad_middleware(ctx, next):
    try:
        await next()
    except Exception:
        pass  # Swallowed - no one knows there was an error
```

✅ **Do: Log and/or re-raise**

```python
@middleware
async def good_middleware(ctx, next):
    try:
        await next()
    except Exception as e:
        logger.error(f"Error in {ctx.event_type}: {e}")
        raise  # Re-raise for other middleware/error handling
```

## Real-World Examples

### Distributed Tracing

```python
import opentelemetry

@middleware
async def tracing_middleware(ctx, next):
    """Add distributed tracing"""
    with tracer.start_as_current_span(f"event.{ctx.event_type}") as span:
        span.set_attribute("subject", ctx.subject.name)
        span.set_attribute("event_type", ctx.event_type)

        try:
            await next()
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(e)
            raise
```

### Multi-Tenancy

```python
@middleware
async def tenant_middleware(ctx, next):
    """Enforce tenant isolation"""
    tenant = ctx.payload.get("tenant_id")

    if not tenant:
        logger.warning("Missing tenant_id")
        return  # Short-circuit

    # Store tenant in metadata for handlers
    ctx.set_metadata("tenant_id", tenant)

    # Validate subject belongs to tenant
    subject_tenant = ctx.subject.get_ext("tenant_id")
    if subject_tenant and subject_tenant != tenant:
        logger.warning(f"Tenant mismatch: {tenant} vs {subject_tenant}")
        return

    await next()
```

### Audit Logging

```python
@middleware
async def audit_middleware(ctx, next):
    """Audit all events"""
    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": ctx.event_type,
        "subject": ctx.subject.name,
        "payload": ctx.payload,
        "user": ctx.payload.get("user_id"),
    }

    await next()

    # Log after successful execution
    audit_entry["status"] = "success"
    await audit_logger.log(audit_entry)
```

## What's Next?

- [Container & DI](CONTAINER_DI.md) - Dependency injection
- [Testing](TESTING.md) - Testing strategies
- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [API Reference](API_REFERENCE.md) - Complete API
