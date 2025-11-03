# Advanced Patterns

Production-ready patterns and best practices for KRules applications.

## Event Cascade Design

### Planning Event Flows

Design event flows as directed acyclic graphs (DAGs):

```python
# Order processing flow
"""
order.submitted
    ↓
order.validated
    ↓
payment.process
    ↓
payment.completed
    ↓
order.ship
    ↓
order.shipped
"""

@on("order.submitted")
async def validate_order(ctx):
    if ctx.subject.get("total") > 0:
        await ctx.emit("order.validated")

@on("order.validated")
async def process_payment(ctx):
    # Process payment...
    await ctx.emit("payment.completed")

@on("payment.completed")
async def ship_order(ctx):
    ctx.subject.set("status", "shipped")
    await ctx.emit("order.shipped")
```

### Avoiding Infinite Loops

**Problem:** Handler modifies property that triggers itself.

```python
# ❌ Infinite loop
@on(SUBJECT_PROPERTY_CHANGED)
async def bad_handler(ctx):
    # This triggers the same handler again!
    ctx.subject.set("counter", lambda c: c + 1)
```

**Solutions:**

**1. Use muted properties:**
```python
@on(SUBJECT_PROPERTY_CHANGED)
async def good_handler(ctx):
    ctx.subject.set("counter", lambda c: c + 1, muted=True)
```

**2. Use filters:**
```python
@on(SUBJECT_PROPERTY_CHANGED)
@when(lambda ctx: ctx.property_name != "counter")
async def filtered_handler(ctx):
    ctx.subject.set("counter", lambda c: c + 1)
```

**3. Use extended properties:**
```python
@on(SUBJECT_PROPERTY_CHANGED)
async def handler_with_ext(ctx):
    ctx.subject.set_ext("internal_counter", lambda c: c + 1)
```

### Circuit Breaker Pattern

Prevent cascading failures:

```python
from collections import defaultdict
from datetime import datetime, timedelta

error_counts = defaultdict(lambda: {"count": 0, "reset_time": datetime.now()})

@middleware
async def circuit_breaker(ctx, next):
    """Circuit breaker for subjects"""
    subject_key = ctx.subject.name
    state = error_counts[subject_key]

    # Reset after timeout
    if datetime.now() > state["reset_time"]:
        state["count"] = 0
        state["reset_time"] = datetime.now() + timedelta(minutes=5)

    # Check if circuit is open
    if state["count"] > 5:
        logger.warning(f"Circuit open for {subject_key}")
        return  # Short-circuit

    try:
        await next()
        # Success - reset counter
        state["count"] = 0
    except Exception as e:
        # Error - increment counter
        state["count"] += 1
        if state["count"] > 5:
            logger.error(f"Circuit opened for {subject_key}")
        raise
```

## Error Handling

### Per-Handler Error Isolation

Errors in one handler don't affect others (built-in):

```python
@on("user.action")
async def handler1(ctx):
    raise Exception("Error!")  # Doesn't affect handler2

@on("user.action")
async def handler2(ctx):
    print("Still runs!")  # Executes despite handler1 error
```

### Global Error Middleware

Handle all errors centrally:

```python
@middleware
async def error_handler(ctx, next):
    """Global error handler"""
    try:
        await next()
    except Exception as e:
        logger.error(f"Error in {ctx.event_type}: {e}", exc_info=True)

        # Emit error event
        await ctx.emit("error.handler_failed", {
            "original_event": ctx.event_type,
            "error": str(e),
            "subject": ctx.subject.name,
            "timestamp": datetime.now().isoformat()
        })
```

### Dead Letter Queue Pattern

```python
@on("error.handler_failed")
async def send_to_dlq(ctx):
    """Send failed events to dead letter queue"""
    dlq_subject = container.subject(f"dlq-{uuid.uuid4()}")
    dlq_subject.set("original_event", ctx.payload["original_event"])
    dlq_subject.set("error", ctx.payload["error"])
    dlq_subject.set("subject_name", ctx.payload["subject"])
    dlq_subject.set("timestamp", ctx.payload["timestamp"])
    dlq_subject.store()

    # Optionally: send to external DLQ service
    # await dlq_service.send(ctx.payload)
```

### Retry Pattern

```python
@on("api.call")
@when(lambda ctx: ctx.subject.get("retry_count", 0) < 3)
async def call_with_retry(ctx):
    """Retry failed API calls"""
    try:
        response = await api_client.call()

        if response.ok:
            ctx.subject.set("retry_count", 0, muted=True)
            ctx.subject.set("last_success", datetime.now().isoformat())
        else:
            raise Exception(f"API error: {response.status}")

    except Exception as e:
        # Increment retry count
        retry_count = ctx.subject.get("retry_count", 0) + 1
        ctx.subject.set("retry_count", retry_count, muted=True)

        if retry_count < 3:
            # Exponential backoff
            await asyncio.sleep(2 ** retry_count)
            await ctx.emit("api.call")  # Retry
        else:
            # Max retries reached
            await ctx.emit("api.call_failed", {
                "error": str(e),
                "retries": retry_count
            })
```

## Performance Optimization

### Batch Property Updates

```python
# ✅ Efficient: batch updates
user = container.subject("user-123")
for i in range(100):
    user.set(f"field{i}", i)  # Cached
user.store()  # Single write

# ❌ Inefficient: individual writes
user = container.subject("user-123")
for i in range(100):
    user.set(f"field{i}", i, use_cache=False)  # 100 writes!
```

### Cache Strategy

```python
# High-frequency updates: disable cache
@on("sensor.reading")
async def record_reading(ctx):
    sensor = ctx.subject
    # Atomic write to storage
    sensor.set("last_reading", ctx.payload["value"], use_cache=False)

# Batch updates: use cache
@on("user.profile_update")
async def update_profile(ctx):
    user = ctx.subject
    user.set("name", ctx.payload["name"])
    user.set("email", ctx.payload["email"])
    user.set("address", ctx.payload["address"])
    user.store()  # Single write
```

### Handler Concurrency

Handlers execute concurrently by default:

```python
@on("device.reading")
async def process_reading(ctx):
    # Multiple devices can process concurrently
    await heavy_computation(ctx.subject)
```

## Monitoring & Observability

### Logging Middleware

```python
import logging

logger = logging.getLogger(__name__)

@middleware
async def logging_middleware(ctx, next):
    """Log all events"""
    logger.info(
        "Event",
        extra={
            "event_type": ctx.event_type,
            "subject": ctx.subject.name,
            "payload": ctx.payload
        }
    )
    await next()
```

### Metrics Middleware

```python
from prometheus_client import Counter, Histogram

event_counter = Counter('krules_events_total', 'Total events', ['event_type'])
event_duration = Histogram('krules_event_duration_seconds', 'Event duration', ['event_type'])

@middleware
async def metrics_middleware(ctx, next):
    """Collect metrics"""
    event_counter.labels(event_type=ctx.event_type).inc()

    with event_duration.labels(event_type=ctx.event_type).time():
        await next()
```

### Distributed Tracing

```python
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

tracer = trace.get_tracer(__name__)

@middleware
async def tracing_middleware(ctx, next):
    """Add distributed tracing"""
    with tracer.start_as_current_span(f"event.{ctx.event_type}") as span:
        span.set_attribute("event.type", ctx.event_type)
        span.set_attribute("subject.name", ctx.subject.name)

        try:
            await next()
            span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR))
            span.record_exception(e)
            raise
```

### Event Debugging

```python
@middleware
async def debug_middleware(ctx, next):
    """Debug event flow"""
    debug = os.getenv("DEBUG_EVENTS", "false").lower() == "true"

    if debug:
        print(f"\n=== Event: {ctx.event_type} ===")
        print(f"Subject: {ctx.subject.name}")
        print(f"Payload: {json.dumps(ctx.payload, indent=2)}")

        start = time.time()
        await next()
        duration = time.time() - start

        print(f"Duration: {duration:.3f}s")
        print("=" * 50)
    else:
        await next()
```

## Scalability

### Horizontal Scaling

KRules applications scale horizontally with shared storage:

```python
# Each instance uses Redis
container = KRulesContainer()
redis_factory = create_redis_storage(
    url="redis://shared-redis:6379",
    key_prefix="app:"
)
container.subject_storage.override(providers.Object(redis_factory))

# Multiple instances can process events concurrently
# Redis ensures consistency
```

### Event Partitioning

Partition events by subject for parallel processing:

```python
def get_partition(subject_name: str, num_partitions: int) -> int:
    """Determine partition for subject"""
    return hash(subject_name) % num_partitions

@middleware
async def partition_middleware(ctx, next):
    """Route to appropriate partition"""
    partition = get_partition(ctx.subject.name, num_partitions=4)
    ctx.set_metadata("partition", partition)

    # Only process if this instance handles this partition
    my_partition = int(os.getenv("PARTITION_ID", "0"))
    if partition == my_partition:
        await next()
```

### Load Balancing

Use message queue for load balancing:

```python
# Producer
async def emit_to_queue(event_type, subject, payload):
    """Emit event to message queue"""
    message = {
        "event_type": event_type,
        "subject_name": subject.name,
        "payload": payload
    }
    await queue.send(message)

# Consumer (multiple instances)
async def consume_from_queue():
    """Process events from queue"""
    async for message in queue.receive():
        subject = container.subject(message["subject_name"])
        await emit(message["event_type"], subject, message["payload"])
```

## Event Naming Conventions

Consistent naming improves maintainability:

```python
# Pattern: {entity}.{action}
"user.created"
"user.updated"
"user.deleted"
"order.submitted"
"order.validated"
"payment.processed"

# For property changes, use built-in constants
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED
@on(SUBJECT_PROPERTY_CHANGED)

# For errors
"error.handler_failed"
"error.validation_failed"

# For alerts
"alert.critical"
"alert.warning"
```

## What's Next?

- [Testing](TESTING.md) - Testing strategies
- [API Reference](API_REFERENCE.md) - Complete API
