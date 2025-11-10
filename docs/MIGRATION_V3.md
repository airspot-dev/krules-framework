# Migration Guide: KRules 2.x → 3.0 (Full Async)

## Overview

KRules 3.0 completes the async migration started in 2.0 with **breaking changes** for full async/await support across the entire framework.

**What's changed:**
- ✅ All Subject methods are now async (`await subject.set()`, `await subject.get()`)
- ✅ All event handlers must be `async def`
- ✅ Storage backends are fully async (Redis, PostgreSQL)
- ✅ CloudEvents dispatcher is async
- ✅ All filters must be async if they access Subject
- ✅ Better performance with non-blocking I/O
- ✅ Simpler architecture (no AwaitableResult, no property proxies)

**What's removed:**
- ❌ Sync handlers (no more `def handle(ctx):`)
- ❌ Magic property access (no more `user.name = "X"`)
- ❌ `AwaitableResult` class
- ❌ `wrapt` dependency
- ❌ Sync Subject API

## Breaking Changes

### 1. Subject Methods are Async

**Before (2.x):**
```python
user = container.subject("user-123")
user.set("name", "John")
user.set("age", 30)
name = user.get("name")
user.store()  # sync
```

**After (3.0):**
```python
user = container.subject("user-123")
await user.set("name", "John")
await user.set("age", 30)
name = await user.get("name")
await user.store()  # async
```

**All async methods:**
- `await subject.set(prop, value, muted=False)`
- `await subject.get(prop, default=None)`
- `await subject.has(prop)`
- `await subject.keys()`
- `await subject.delete(prop, muted=False)`
- `await subject.set_ext(prop, value)`
- `await subject.get_ext(prop, default=None)`
- `await subject.has_ext(prop)`
- `await subject.get_ext_props()`
- `await subject.delete_ext(prop)`
- `await subject.store()`
- `await subject.flush()`
- `await subject.dict()`

**Still sync (no await):**
- `subject.event_info()` - metadata access only
- `str(subject)` - returns subject name
- `repr(subject)` - returns `Subject<name>`

### 2. All Handlers Must Be Async

**Before (2.x - both sync and async were supported):**
```python
@on("user.created")
def handle_user(ctx):  # sync was allowed
    user = ctx.subject
    user.set("status", "active")
```

**After (3.0 - only async):**
```python
@on("user.created")
async def handle_user(ctx):  # must be async
    user = ctx.subject
    await user.set("status", "active")
```

**Error if handler is sync:**
```python
@on("user.created")
def sync_handler(ctx):  # ❌ Will raise TypeError
    pass

# TypeError: Handler 'sync_handler' must be async.
# Change 'def sync_handler(ctx)' to 'async def sync_handler(ctx)'
```

### 3. Filters Must Be Async if Accessing Subject

**Before (2.x - sync filters could access Subject):**
```python
def is_active(ctx):
    return ctx.subject.get("status") == "active"  # sync

@on("action.execute")
@when(is_active)
async def handle_action(ctx):
    pass
```

**After (3.0 - filters accessing Subject must be async):**
```python
async def is_active(ctx):
    return await ctx.subject.get("status") == "active"  # async

@on("action.execute")
@when(is_active)
async def handle_action(ctx):
    pass
```

**Sync filters still work if they don't access Subject:**
```python
# ✅ OK: sync filter without Subject access
@on("admin.action")
@when(lambda ctx: ctx.payload.get("role") == "admin")
async def handle_admin(ctx):
    pass
```

### 4. Property Access Syntax Removed

**Before (2.x - magic property access):**
```python
user = container.subject("user-123")
user.name = "John"  # Magic __setattr__
print(user.name)     # Magic __getattr__
if "name" in user:   # Magic __contains__
    del user.name    # Magic __delattr__
```

**After (3.0 - explicit async methods only):**
```python
user = container.subject("user-123")
await user.set("name", "John")
print(await user.get("name"))
if await user.has("name"):
    await user.delete("name")
```

**Why removed:**
- Python magic methods can't be async
- Cleaner, more explicit API
- Better IDE type hints
- Reduced complexity (no `AwaitableResult`)

### 5. CloudEvents Dispatcher is Async

**Before (2.x - dispatch was sync):**
```python
dispatcher.dispatch(
    event_type="order.confirmed",
    subject=subject,
    payload={},
    topic="orders"
)
```

**After (3.0 - dispatch is async):**
```python
await dispatcher.dispatch(
    event_type="order.confirmed",
    subject=subject,
    payload={},
    topic="orders"
)
```

**Middleware handles this automatically:**
```python
# In handlers, middleware handles async dispatch
@on("order.created")
async def handler(ctx):
    # Middleware automatically awaits dispatch
    await ctx.emit("order.confirmed", {...}, topic="orders")
```

## Migration Steps

### Step 1: Update All Handler Definitions

Search for all `@on` handlers and add `async`:

```bash
# Find all handlers missing async
grep -r "^def.*ctx" --include="*.py" .
```

**Convert each handler:**
```python
# Before
@on("event.type")
def handler(ctx):
    pass

# After
@on("event.type")
async def handler(ctx):
    pass
```

### Step 2: Add `await` to All Subject Method Calls

Search for Subject method calls and add `await`:

```bash
# Find Subject method calls (may need manual review)
grep -r "subject\.\(set\|get\|delete\|store\|flush\)" --include="*.py" .
```

**Common patterns:**
```python
# set()
subject.set("key", "value")
→ await subject.set("key", "value")

# get()
value = subject.get("key")
→ value = await subject.get("key")

# has()
if subject.has("key"):
→ if await subject.has("key"):

# store()
subject.store()
→ await subject.store()

# delete()
subject.delete("key")
→ await subject.delete("key")

# flush()
subject.flush()
→ await subject.flush()

# dict()
data = subject.dict()
→ data = await subject.dict()

# keys()
keys = subject.keys()
→ keys = await subject.keys()

# Extended properties
subject.set_ext("key", "value")
→ await subject.set_ext("key", "value")

value = subject.get_ext("key")
→ value = await subject.get_ext("key")
```

### Step 3: Update Filters Accessing Subject

Find filters that call Subject methods and make them async:

```python
# Before
def check_status(ctx):
    return ctx.subject.get("status") == "active"

# After
async def check_status(ctx):
    return await ctx.subject.get("status") == "active"
```

**Lambda filters:**
```python
# Before - can't access Subject methods easily
@when(lambda ctx: ctx.subject.get("status") == "active")

# After - use named async function
async def is_active(ctx):
    return await ctx.subject.get("status") == "active"

@when(is_active)
```

### Step 4: Update Tests to pytest-asyncio

**Before (2.x):**
```python
def test_handler():
    subject = container.subject("test")
    subject.set("value", 42)
    assert subject.get("value") == 42
```

**After (3.0):**
```python
@pytest.mark.asyncio
async def test_handler():
    subject = container.subject("test")
    await subject.set("value", 42)
    assert await subject.get("value") == 42
```

**Add to pyproject.toml:**
```toml
[dependency-groups]
test = [
    "pytest>=7.0.0",
    "pytest-asyncio>=1.2.0",
]

[tool.pytest.ini_options]
asyncio_mode = "strict"
```

### Step 5: Update Storage Backend Configuration

**Redis storage is now async:**
```python
from redis_subjects_storage import create_redis_storage
from redis.asyncio import Redis

# Create async Redis client
redis_client = await Redis.from_url("redis://localhost:6379/0")

# Use with container
storage_factory = create_redis_storage(
    redis_client=redis_client,
    redis_prefix="app:"
)
container.subject_storage.override(storage_factory)
```

**PostgreSQL storage (new in 3.0):**
```python
from postgres_subjects_storage import create_postgres_storage

storage_factory = create_postgres_storage(
    postgres_url="postgresql://localhost:5432/krules"
)
container.subject_storage.override(storage_factory)
```

## Common Pitfalls

### Pitfall 1: Forgetting `await`

**❌ Error:**
```python
@on("event")
async def handler(ctx):
    subject.set("key", "value")  # Forgot await!
    # RuntimeWarning: coroutine 'Subject.set' was never awaited
```

**✅ Fix:**
```python
@on("event")
async def handler(ctx):
    await subject.set("key", "value")
```

### Pitfall 2: Sync Handler with Async Calls

**❌ Error:**
```python
@on("event")
def handler(ctx):  # Not async!
    await subject.set("key", "value")  # SyntaxError: await outside async
```

**✅ Fix:**
```python
@on("event")
async def handler(ctx):
    await subject.set("key", "value")
```

### Pitfall 3: Lambda Filters with Subject Access

**❌ Error:**
```python
@when(lambda ctx: ctx.subject.get("status") == "active")
# RuntimeWarning: coroutine never awaited
```

**✅ Fix - use named async function:**
```python
async def is_active(ctx):
    return await ctx.subject.get("status") == "active"

@when(is_active)
```

### Pitfall 4: Testing Without pytest-asyncio

**❌ Error:**
```python
def test_handler():  # Not async
    await subject.set("key", "value")  # SyntaxError
```

**✅ Fix:**
```python
@pytest.mark.asyncio
async def test_handler():
    await subject.set("key", "value")
```

### Pitfall 5: Mixing Sync and Async Storage

**❌ Error:**
```python
# Using sync redis-py with async framework
from redis import Redis  # Wrong!
client = Redis.from_url("redis://localhost")
```

**✅ Fix:**
```python
# Use async redis
from redis.asyncio import Redis
client = await Redis.from_url("redis://localhost")
```

## Performance Benefits

### Non-Blocking I/O

**Before (2.x with sync storage):**
```python
@on("batch.process")
async def process_batch(ctx):
    for i in range(100):
        user = container.subject(f"user-{i}")
        user.set("processed", True)
        user.store()  # Blocks! Next user waits
```

**After (3.0 with async storage):**
```python
@on("batch.process")
async def process_batch(ctx):
    async def process_user(i):
        user = container.subject(f"user-{i}")
        await user.set("processed", True)
        await user.store()  # Non-blocking!

    # Process all users concurrently
    await asyncio.gather(*[process_user(i) for i in range(100)])
```

**Result:** 10-100x faster for I/O-bound workloads!

### Connection Pooling

Async storage backends automatically use connection pooling:

```python
# Redis: reuses connections from pool
for i in range(1000):
    user = container.subject(f"user-{i}")
    await user.set("value", i)  # No connection overhead
    await user.store()

# PostgreSQL: same pool efficiency
```

## Before/After Examples

### Example 1: Simple Handler

**Before (2.x):**
```python
@on("user.login")
async def handle_login(ctx):
    user = ctx.subject
    user.set("last_login", datetime.now())
    user.set("login_count", lambda c: c + 1)
    user.store()
```

**After (3.0):**
```python
@on("user.login")
async def handle_login(ctx):
    user = ctx.subject
    await user.set("last_login", datetime.now())
    await user.set("login_count", lambda c: c + 1)
    await user.store()
```

**Changes:** Added `await` to all Subject methods.

### Example 2: Property Change Handler

**Before (2.x):**
```python
@on("subject-property-changed")
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_overheat(ctx):
    ctx.subject.set("alert_sent", True)
    await ctx.emit("alert.overheat", {"temp": ctx.new_value})
```

**After (3.0):**
```python
@on("subject-property-changed")
@when(lambda ctx: ctx.property_name == "temperature")
@when(lambda ctx: ctx.new_value > 80)
async def alert_overheat(ctx):
    await ctx.subject.set("alert_sent", True)
    await ctx.emit("alert.overheat", {"temp": ctx.new_value})
```

**Changes:** Added `await` to `set()`.

### Example 3: Conditional Handler with Subject Filter

**Before (2.x):**
```python
def is_premium(ctx):
    return ctx.subject.get("tier") == "premium"

@on("feature.use")
@when(is_premium)
async def premium_feature(ctx):
    ctx.subject.set("credits", lambda c: c - 1)
```

**After (3.0):**
```python
async def is_premium(ctx):
    return await ctx.subject.get("tier") == "premium"

@on("feature.use")
@when(is_premium)
async def premium_feature(ctx):
    await ctx.subject.set("credits", lambda c: c - 1)
```

**Changes:** Made filter async, added `await` to both `get()` and `set()`.

### Example 4: Batch Processing

**Before (2.x):**
```python
@on("batch.import")
async def import_users(ctx):
    users = ctx.payload["users"]
    for user_data in users:
        user = container.subject(f"user-{user_data['id']}")
        user.set("name", user_data["name"])
        user.set("email", user_data["email"])
        user.store()
```

**After (3.0):**
```python
@on("batch.import")
async def import_users(ctx):
    users = ctx.payload["users"]

    async def import_user(user_data):
        user = container.subject(f"user-{user_data['id']}")
        await user.set("name", user_data["name"])
        await user.set("email", user_data["email"])
        await user.store()

    # Process all users concurrently (faster!)
    await asyncio.gather(*[import_user(u) for u in users])
```

**Changes:** Added `await` + refactored to use `asyncio.gather()` for parallel processing.

## Checklist

Use this checklist to ensure complete migration:

- [ ] All handlers use `async def`
- [ ] All `subject.set()` calls use `await`
- [ ] All `subject.get()` calls use `await`
- [ ] All `subject.store()` calls use `await`
- [ ] All `subject.delete()` calls use `await`
- [ ] All `subject.flush()` calls use `await`
- [ ] All `subject.has()` calls use `await`
- [ ] All `subject.keys()` calls use `await`
- [ ] All `subject.dict()` calls use `await`
- [ ] All `subject.set_ext()` calls use `await`
- [ ] All `subject.get_ext()` calls use `await`
- [ ] All `subject.delete_ext()` calls use `await`
- [ ] All `subject.get_ext_props()` calls use `await`
- [ ] All filters accessing Subject are async
- [ ] All tests use `@pytest.mark.asyncio`
- [ ] All test functions are `async def`
- [ ] Storage backend uses async client (redis.asyncio, asyncpg)
- [ ] `pytest-asyncio` installed in test dependencies
- [ ] No `RuntimeWarning: coroutine never awaited` errors
- [ ] All tests passing

## Support

- **GitHub Issues:** https://github.com/airspot-dev/krules-framework/issues
- **Documentation:** https://github.com/airspot-dev/krules-framework/tree/main/docs
- **Examples:** https://github.com/airspot-dev/krules-framework/tree/main/examples

## See Also

- [ASYNC_IN_SYNC.md](./ASYNC_IN_SYNC.md) - Using async KRules in sync contexts (Celery)
- [SUBJECTS.md](./SUBJECTS.md) - Complete Subject API reference
- [EVENT_HANDLERS.md](./EVENT_HANDLERS.md) - Handler patterns and best practices
- [STORAGE_BACKENDS.md](./STORAGE_BACKENDS.md) - Storage configuration (Redis, PostgreSQL)
