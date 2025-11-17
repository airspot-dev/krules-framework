# Using Async KRules in Sync Contexts

## Overview

KRules 3.0 is fully async, but many production systems still use synchronous frameworks like **Celery**. This guide shows how to integrate async KRules handlers with sync codebases.

**Common use cases:**
- Celery task queues with KRules event handlers
- Legacy sync applications migrating to async
- Mixed sync/async architectures during transition periods
- WSGI applications (Flask, Django) calling KRules handlers

**Key principle:** Use `asyncio.run()` to create an event loop and execute async code from sync contexts.

## Quick Start

### Basic Pattern

```python
import asyncio
from celery import Celery
from krules_core.container import KRulesContainer

app = Celery('tasks')
container = KRulesContainer()

@app.task
def process_order(order_id):
    """Sync Celery task calling async KRules handler."""
    # Create subject and trigger event
    subject = container.subject(f"order-{order_id}")

    # Use asyncio.run() to execute async code
    asyncio.run(
        container.event_bus().emit(
            event_type="order.process",
            subject=subject,
            payload={"order_id": order_id}
        )
    )
```

**How it works:**
1. Celery calls sync task `process_order()`
2. `asyncio.run()` creates a new event loop
3. KRules async handlers execute in that loop
4. Loop closes when emit() completes
5. Control returns to Celery

## Production-Proven Celery Integration

This section documents the **recommended pattern** for integrating async KRules with Celery, based on real production deployments (Companion, TradingLab).

### Worker-Level Event Loop with --pool=solo

**Production status:** ✅ Verified in multiple production systems

**Key advantages:**
- Single event loop per worker (zero overhead)
- Compatible with async Redis clients (KRules subjects storage)
- Thread-safe implementation
- Simple to implement and maintain
- No additional dependencies (no gevent/eventlet needed)
- Proven for high-frequency scenarios (1000+ tasks/sec)

### Implementation

#### Step 1: Create utils.py helper module

```python
# utils.py - Async event loop management for Celery workers
"""
Utilities for async task execution in Celery workers.

This module provides a worker-wide event loop to avoid the overhead
of creating/destroying event loops for each async task, and ensures
compatibility with async Redis clients used by KRules Framework.
"""
import asyncio
import threading
from typing import Coroutine, TypeVar

import logfire

# Worker-wide event loop
_worker_loop = None
_worker_loop_lock = threading.Lock()

T = TypeVar('T')


def get_or_create_event_loop() -> asyncio.AbstractEventLoop:
    """
    Get or create a persistent event loop for this Celery worker.

    This function ensures that all async tasks in the same worker process
    share the same event loop, which is critical for:
    - Redis async client compatibility (KRules subjects storage)
    - Connection pooling efficiency
    - Zero overhead for event loop creation/destruction

    Thread-safe implementation using a lock to prevent race conditions.

    Returns:
        asyncio.AbstractEventLoop: The worker-wide event loop
    """
    global _worker_loop

    with _worker_loop_lock:
        if _worker_loop is None or _worker_loop.is_closed():
            logfire.info("Creating new worker-wide event loop")
            _worker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_worker_loop)
        return _worker_loop


def run_async(coro: Coroutine[None, None, T]) -> T:
    """
    Execute an async coroutine using the worker-wide event loop.

    This function replaces the pattern:
        asyncio.run(async_function())

    With a worker-wide event loop that persists across task executions:
        run_async(async_function())

    Benefits:
    - Zero event loop creation overhead (~0.5ms saved per task)
    - Redis client compatibility (no "different loop" errors)
    - Connection pooling across tasks
    - Production-ready for high-frequency tasks (1000+ tasks/sec)

    Args:
        coro: The async coroutine to execute

    Returns:
        T: The result of the coroutine execution

    Example:
        @app.task
        def celery_task(symbol: str, data: dict):
            return run_async(_async_implementation(symbol, data))
    """
    loop = get_or_create_event_loop()
    return loop.run_until_complete(coro)
```

#### Step 2: Configure Celery app and KRules handlers

```python
# tasks.py
from celery import Celery
from krules_core.container import KRulesContainer
from .utils import run_async

app = Celery('tasks', broker='redis://localhost:6379/0')
container = KRulesContainer()

# KRules setup
on, when, middleware, emit = container.handlers()

# Define async KRules handlers
@on("order.created")
async def handle_order_created(ctx):
    """Async KRules handler - runs in worker event loop."""
    await ctx.subject.set("status", "pending")
    await ctx.subject.set("created_at", datetime.now())
    await ctx.subject.store()
```

#### Step 3: Define Celery tasks using run_async helper

```python
# tasks.py (continued)

@app.task
def create_order(order_data):
    """
    Sync Celery task calling async KRules code.

    Uses run_async() to execute async event emission in the
    worker-wide event loop with zero overhead.
    """
    subject = container.subject(f"order-{order_data['id']}")

    # Use run_async helper to execute async code
    run_async(
        container.event_bus().emit(
            event_type="order.created",
            subject=subject,
            payload=order_data
        )
    )

    return f"Order {order_data['id']} created"


async def _send_callback_async(channels, subscription, entity_id, entity_data, message):
    """
    Internal async implementation.

    Pattern: Define complex async logic in separate async functions,
    then call them via run_async() from Celery tasks.
    """
    krules = container.krules()

    payload = {
        "subscription": subscription,
        "id": entity_id,
        "state": entity_data,
        "message": message,
    }

    for channel in channels:
        # Process each channel asynchronously
        await process_channel(channel, payload)

    # Emit events via KRules
    await krules.event_bus().emit(
        "callback.sent",
        f"entity|{subscription}|{entity_id}",
        payload
    )


@app.task
def schedule(subscription, group, entity_id, message, channels):
    """
    Example from Companion production system.

    Fetches data from Firestore and processes it via async KRules handlers.
    """
    # Sync operations (Firestore fetch, etc.)
    db = container.firestore_client()
    doc_ref = db.collection(f"{subscription}/groups/{group}").document(entity_id)
    entity_data = doc_ref.get().to_dict()

    if entity_data is None:
        # Handle missing data via KRules event
        run_async(
            container.krules().event_bus().emit(
                "callback.entity_notfound",
                f"entity|{subscription}|{entity_id}",
                {"group": group}
            )
        )
    else:
        # Process entity via async function
        run_async(_send_callback_async(channels, subscription, entity_id, entity_data, message))
```

#### Step 4: Run Celery worker with --pool=solo (CRITICAL)

```bash
# Use --pool=solo for single-threaded async compatibility
celery -A tasks worker --pool=solo --loglevel=info

# For production/Kubernetes deployments with queue
celery -A tasks worker --pool=solo -Q my-queue --loglevel=info

# With autoscaling (scale worker replicas, not pool concurrency)
# Deploy multiple worker pods/instances instead
```

**Why --pool=solo is critical:**
- Ensures single-threaded execution (compatible with shared event loop)
- No concurrency issues with async Redis clients or other async resources
- Simpler than gevent/eventlet (no monkey patching, no C extension issues)
- Works perfectly with async/await code
- Scale horizontally by running multiple worker instances/pods

**DO NOT use:**
- `--pool=prefork` - Creates multiple processes, event loop not shared
- `--pool=gevent` - Requires additional dependencies, monkey patching issues
- `--pool=eventlet` - Similar issues to gevent
- `--concurrency=N` - Not needed with solo pool, scale with worker instances instead

### Deployment Example (Kubernetes)

```yaml
# From Companion production deployment
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: backend-api-v2-worker
spec:
  replicas: 3  # Scale by adding replicas, not pool concurrency
  template:
    spec:
      containers:
      - name: worker
        image: backend-api-v2:latest
        command: ["uv", "run", "celery"]
        args:
          - "-A"
          - "backend_api_v2.tasks"
          - "worker"
          - "--loglevel=info"
          - "-Q"
          - "backend-api-v2"
          - "--pool=solo"  # CRITICAL: solo pool for async compatibility
        env:
          - name: CELERY_BROKER
            value: "redis://redis:6379/0"
          - name: CELERY_BACKEND
            value: "redis://redis:6379/1"
```

### Pros and Cons

**Pros:**
- ✅ Production-proven (Companion, TradingLab systems)
- ✅ Zero event loop overhead
- ✅ Maximum compatibility with async libraries (Redis, KRules, etc.)
- ✅ Simple implementation (no Celery signals needed)
- ✅ Thread-safe with lock
- ✅ Easy to debug and maintain
- ✅ No additional dependencies

**Cons:**
- ⚠️ Single task execution per worker (mitigate: scale horizontally with multiple workers)
- ⚠️ Requires --pool=solo flag (easy to forget, document in README)

## Scaling Strategy

Since `--pool=solo` runs one task at a time per worker, scale by deploying multiple worker instances rather than increasing pool concurrency.

### Horizontal Scaling Examples

**Kubernetes (StatefulSet):**
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: celery-worker
spec:
  replicas: 5  # Scale horizontally
  template:
    spec:
      containers:
      - name: worker
        command: ["celery", "-A", "tasks", "worker", "--pool=solo"]
```

**Docker Compose:**
```yaml
services:
  worker:
    image: myapp:latest
    command: celery -A tasks worker --pool=solo
    deploy:
      replicas: 5  # Scale horizontally
```

**Systemd (multiple services):**
```bash
# Create multiple systemd service files
# /etc/systemd/system/celery-worker@.service

[Service]
ExecStart=/usr/bin/celery -A tasks worker --pool=solo -n worker%i@%h

# Enable multiple instances
systemctl enable celery-worker@{1..5}
```

## Performance Optimization

The recommended pattern (worker-level event loop with `--pool=solo`) provides excellent performance for typical workloads (100-1000+ events/sec). Here are additional optimizations for high-throughput scenarios.

### Optimization Tips

**1. Use connection pooling:**
```python
from redis.asyncio import Redis
from redis_subjects_storage import create_redis_storage

# Create shared Redis client (reused across events)
redis_client = await Redis.from_url(
    "redis://localhost:6379/0",
    max_connections=50  # Connection pool
)

storage_factory = create_redis_storage(redis_client=redis_client)
container.subject_storage.override(storage_factory)
```

**2. Batch operations when possible:**
```python
async def _process_batch_async(order_ids):
    """Process multiple orders concurrently."""
    async def process_one(order_id):
        subject = container.subject(f"order-{order_id}")
        await container.event_bus().emit("order.process", subject, {})

    # Concurrent processing within single task
    await asyncio.gather(*[process_one(oid) for oid in order_ids])

@app.task
def process_batch(order_ids):
    """Process multiple orders in single Celery task."""
    run_async(_process_batch_async(order_ids))
```

**3. Reuse subjects:**
```python
async def _update_order_async(order_id, updates):
    """Reuse subject for multiple operations."""
    subject = container.subject(f"order-{order_id}")

    # Multiple sets without intermediate stores
    for key, value in updates.items():
        await subject.set(key, value)

    # Single store at end
    await subject.store()

@app.task
def update_order(order_id, updates):
    run_async(_update_order_async(order_id, updates))
```

**4. Scale horizontally:**
```bash
# Don't increase concurrency - scale worker replicas instead
# ❌ Wrong: celery -A tasks worker --pool=solo --concurrency=10
# ✅ Right: Deploy 10 worker instances with --pool=solo
```

## Common Pitfalls

### Pitfall 1: Forgetting --pool=solo Flag

**❌ Error:**
```bash
# Starting worker without --pool=solo
celery -A tasks worker --loglevel=info

# Or using wrong pool
celery -A tasks worker --pool=prefork
```

**Symptoms:**
- `RuntimeError: Task attached to a different loop`
- Redis connection errors
- Async handler failures

**✅ Fix:**
```bash
# Always use --pool=solo for KRules async integration
celery -A tasks worker --pool=solo --loglevel=info
```

### Pitfall 2: Using asyncio.run() Instead of run_async()

**❌ Error:**
```python
from .utils import run_async

@app.task
def process_order(order_id):
    subject = container.subject(f"order-{order_id}")

    # ERROR: Creates new event loop instead of using shared one
    asyncio.run(
        container.event_bus().emit("order.process", subject, {})
    )
```

**Issues:**
- New event loop created per task (overhead)
- Redis client errors ("attached to different loop")
- No connection pooling

**✅ Fix:**
```python
from .utils import run_async

@app.task
def process_order(order_id):
    subject = container.subject(f"order-{order_id}")

    # Use run_async to use worker-wide event loop
    run_async(
        container.event_bus().emit("order.process", subject, {})
    )
```

### Pitfall 3: Using Sync Redis Client

**❌ Error:**
```python
from redis import Redis  # Sync Redis!

# Sync Redis with async KRules → blocking I/O
redis_client = Redis.from_url("redis://localhost:6379/0")
storage_factory = create_redis_storage(redis_client=redis_client)
```

**✅ Fix:**
```python
from redis.asyncio import Redis  # Async Redis

# Async Redis for non-blocking I/O
redis_client = await Redis.from_url("redis://localhost:6379/0")
storage_factory = create_redis_storage(redis_client=redis_client)
```

### Pitfall 4: Calling run_async() from Async Context

**❌ Error:**
```python
async def _helper_function():
    # ERROR: run_async() expects to be called from sync context
    run_async(some_other_async_function())
```

**✅ Fix:**
```python
async def _helper_function():
    # Direct await when already in async context
    await some_other_async_function()

# run_async() is only for sync→async boundary (Celery task → async implementation)
@app.task
def celery_task():
    run_async(_helper_function())  # ✅ Correct usage
```

## Production Checklist

- [ ] **CRITICAL**: Workers running with `--pool=solo` flag
- [ ] `utils.py` module with `run_async()` helper implemented
- [ ] Celery tasks using `run_async()` (not `asyncio.run()`)
- [ ] Async Redis client configured (`redis.asyncio.Redis`)
- [ ] Connection pooling configured for storage backends
- [ ] Worker monitoring set up (Flower, CloudWatch, Prometheus, etc.)
- [ ] Error handling tested in async contexts
- [ ] Retry policies configured for failed tasks
- [ ] Logging configured for async operations (logfire, etc.)
- [ ] Worker shutdown behavior tested (graceful cleanup)
- [ ] Timeouts configured for long-running handlers
- [ ] Health checks configured for workers
- [ ] Horizontal scaling tested (multiple worker instances)
- [ ] Worker configuration documented in README (emphasize `--pool=solo`)
- [ ] Alerts configured for task failures
- [ ] Dead letter queues configured for failed tasks
- [ ] Performance benchmarked under expected load

## Support

- **GitHub Issues:** https://github.com/airspot-dev/krules-framework/issues
- **Documentation:** https://github.com/airspot-dev/krules-framework/tree/main/docs
- **Examples:** https://github.com/airspot-dev/krules-framework/tree/main/examples

## See Also

- [MIGRATION_V3.md](./MIGRATION_V3.md) - Full async migration guide (2.x → 3.0)
- [SUBJECTS.md](./SUBJECTS.md) - Complete Subject API reference
- [EVENT_HANDLERS.md](./EVENT_HANDLERS.md) - Handler patterns and best practices
- [STORAGE_BACKENDS.md](./STORAGE_BACKENDS.md) - Storage configuration (Redis, PostgreSQL)
