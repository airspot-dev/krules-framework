# Testing

KRules is designed for testability. This guide covers testing strategies for handlers, event flows, and storage backends.

## Test Setup

### Basic Pytest Setup

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.fixture
def container():
    """Create fresh container for each test"""
    return KRulesContainer()

@pytest.mark.asyncio
async def test_example(container):
    on, when, middleware, emit = container.handlers()
    # Test code...
```

### Async Tests

Use `pytest-asyncio` for async handlers:

```bash
pip install pytest-asyncio
```

```python
# pytest.ini
[pytest]
asyncio_mode = auto
```

```python
@pytest.mark.asyncio
async def test_async_handler():
    # Test async code
    pass
```

## Testing Handlers

### Basic Handler Test

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.mark.asyncio
async def test_handler():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    results = []

    @on("user.created")
    async def handler(ctx):
        results.append(ctx.event_type)
        ctx.subject.set("status", "active")

    user = container.subject("test-user")
    await emit("user.created", user)

    assert results == ["user.created"]
    assert user.get("status") == "active"
```

### Testing Filters

```python
@pytest.mark.asyncio
async def test_filter():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    results = []

    @on("payment.process")
    @when(lambda ctx: ctx.payload.get("amount") > 0)
    async def handler(ctx):
        results.append("processed")

    user = container.subject("test-user")

    # Should process (amount > 0)
    await emit("payment.process", user, {"amount": 100})
    assert results == ["processed"]

    # Should not process (amount == 0)
    await emit("payment.process", user, {"amount": 0})
    assert results == ["processed"]  # Still just one
```

### Testing Property Changes

```python
from krules_core.event_types import SUBJECT_PROPERTY_CHANGED

@pytest.mark.asyncio
async def test_property_change():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    changes = []

    @on(SUBJECT_PROPERTY_CHANGED)
    @when(lambda ctx: ctx.property_name == "status")
    async def track_status(ctx):
        changes.append((ctx.old_value, ctx.new_value))

    user = container.subject("test-user")
    user.set("status", "active")
    user.set("status", "inactive")

    assert changes == [(None, "active"), ("active", "inactive")]
```

## Testing Event Flows

### Event Cascade Test

```python
@pytest.mark.asyncio
async def test_event_cascade():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    flow = []

    @on("order.created")
    async def create_order(ctx):
        flow.append("created")
        await ctx.emit("order.validate")

    @on("order.validate")
    async def validate_order(ctx):
        flow.append("validated")
        await ctx.emit("payment.process")

    @on("payment.process")
    async def process_payment(ctx):
        flow.append("payment")

    order = container.subject("order-123")
    await emit("order.created", order)

    assert flow == ["created", "validated", "payment"]
```

### Complex Flow Test

```python
@pytest.mark.asyncio
async def test_complex_flow():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    results = {
        "user_created": False,
        "welcome_sent": False,
        "status_set": False
    }

    @on("user.registered")
    async def create_user(ctx):
        results["user_created"] = True
        ctx.subject.set("status", "pending")
        await ctx.emit("email.send_welcome")

    @on(SUBJECT_PROPERTY_CHANGED)
    @when(lambda ctx: ctx.property_name == "status")
    async def on_status_change(ctx):
        results["status_set"] = True

    @on("email.send_welcome")
    async def send_welcome(ctx):
        results["welcome_sent"] = True

    user = container.subject("test-user")
    await emit("user.registered", user)

    assert all(results.values())
    assert user.get("status") == "pending"
```

## Testing Middleware

### Basic Middleware Test

```python
@pytest.mark.asyncio
async def test_middleware():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    execution_order = []

    @middleware
    async def test_mw(ctx, next):
        execution_order.append("before")
        await next()
        execution_order.append("after")

    @on("test.event")
    async def handler(ctx):
        execution_order.append("handler")

    user = container.subject("test")
    await emit("test.event", user)

    assert execution_order == ["before", "handler", "after"]
```

### Middleware Short-Circuit Test

```python
@pytest.mark.asyncio
async def test_middleware_short_circuit():
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    handler_called = []

    @middleware
    async def blocking_mw(ctx, next):
        if ctx.payload.get("blocked"):
            return  # Short-circuit
        await next()

    @on("test.event")
    async def handler(ctx):
        handler_called.append(True)

    user = container.subject("test")

    # Should be blocked
    await emit("test.event", user, {"blocked": True})
    assert handler_called == []

    # Should proceed
    await emit("test.event", user, {"blocked": False})
    assert handler_called == [True]
```

## Testing Subjects

### Subject State Test

```python
@pytest.mark.asyncio
async def test_subject_state():
    container = KRulesContainer()

    user = container.subject("user-123")

    # Test set/get
    user.set("email", "john@example.com")
    assert user.get("email") == "john@example.com"

    # Test default
    assert user.get("missing", default="default") == "default"

    # Test lambda
    user.set("counter", 0)
    user.set("counter", lambda c: c + 1)
    assert user.get("counter") == 1

    # Test existence
    assert "email" in user
    assert "missing" not in user

    # Test delete
    user.delete("email")
    assert "email" not in user
```

### Subject Persistence Test

```python
@pytest.mark.asyncio
async def test_subject_persistence():
    container = KRulesContainer()

    # Create and store
    user = container.subject("user-123")
    user.set("email", "john@example.com")
    user.set("age", 30)
    user.store()

    # Reload (simulates new instance)
    user2 = container.subject("user-123")
    assert user2.get("email") == "john@example.com"
    assert user2.get("age") == 30
```

## Testing with Redis

### Redis Test Setup

```python
import pytest
import redis
from dependency_injector import providers
from krules_core.container import KRulesContainer
from redis_subjects_storage.storage_impl import create_redis_storage

@pytest.fixture
def redis_container():
    """Container with Redis storage"""
    container = KRulesContainer()

    redis_factory = create_redis_storage(
        url="redis://localhost:6379",
        key_prefix="test:"
    )
    container.subject_storage.override(providers.Object(redis_factory))

    yield container

    # Cleanup: delete test keys
    r = redis.Redis.from_url("redis://localhost:6379")
    for key in r.scan_iter("s:test:*"):
        r.delete(key)

@pytest.mark.asyncio
async def test_with_redis(redis_container):
    user = redis_container.subject("user-123")
    user.set("email", "john@example.com")
    user.store()

    # Verify persistence
    user2 = redis_container.subject("user-123")
    assert user2.get("email") == "john@example.com"
```

## Mocking

### Mock External APIs

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
@patch("my_module.external_api_client")
async def test_with_mock_api(mock_api):
    """Test handler that calls external API"""
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    # Setup mock
    mock_api.call_api = AsyncMock(return_value={"status": "ok"})

    @on("user.action")
    async def handler(ctx):
        response = await external_api_client.call_api()
        ctx.subject.set("api_result", response["status"])

    user = container.subject("test-user")
    await emit("user.action", user)

    # Verify mock called
    mock_api.call_api.assert_called_once()

    # Verify result
    assert user.get("api_result") == "ok"
```

### Mock Storage

```python
from unittest.mock import Mock

@pytest.mark.asyncio
async def test_with_mock_storage():
    """Test with mocked storage"""
    container = KRulesContainer()

    # Create mock storage
    mock_storage = Mock()
    mock_storage.load.return_value = ({}, {})

    def mock_factory(name, **kwargs):
        return mock_storage

    container.subject_storage.override(providers.Object(mock_factory))

    # Use subject (will use mock storage)
    user = container.subject("test-user")

    # Verify mock called
    mock_storage.load.assert_called()
```

## Test Patterns

### Arrange-Act-Assert

```python
@pytest.mark.asyncio
async def test_aaa_pattern():
    # Arrange
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    results = []

    @on("test.event")
    async def handler(ctx):
        results.append(ctx.payload["value"])

    # Act
    user = container.subject("test")
    await emit("test.event", user, {"value": 42})

    # Assert
    assert results == [42]
```

### Parameterized Tests

```python
@pytest.mark.parametrize("amount,should_process", [
    (100, True),
    (0, False),
    (-10, False),
])
@pytest.mark.asyncio
async def test_parametrized(amount, should_process):
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    processed = []

    @on("payment.process")
    @when(lambda ctx: ctx.payload.get("amount") > 0)
    async def handler(ctx):
        processed.append(True)

    user = container.subject("test")
    await emit("payment.process", user, {"amount": amount})

    assert (len(processed) > 0) == should_process
```

### Fixture Composition

```python
@pytest.fixture
def container():
    return KRulesContainer()

@pytest.fixture
def handlers(container):
    return container.handlers()

@pytest.fixture
def test_subject(container):
    return container.subject("test-subject")

@pytest.mark.asyncio
async def test_with_fixtures(handlers, test_subject):
    on, when, middleware, emit = handlers

    @on("test.event")
    async def handler(ctx):
        ctx.subject.set("handled", True)

    await emit("test.event", test_subject)

    assert test_subject.get("handled") == True
```

## Integration Tests

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_flow():
    """End-to-end integration test"""
    # Setup real storage
    container = KRulesContainer()
    redis_factory = create_redis_storage(
        url="redis://localhost:6379",
        key_prefix="integration_test:"
    )
    container.subject_storage.override(providers.Object(redis_factory))

    on, when, middleware, emit = container.handlers()

    # Import actual handlers
    from myapp import user_handlers, order_handlers

    # Execute real workflow
    user = container.subject("user-integration-test")
    user.set("email", "test@example.com")
    user.store()

    await emit("user.registered", user)

    # Verify end state
    assert user.get("status") == "active"
    assert user.get("welcome_sent") == True

    # Cleanup
    user.flush()
```

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── test_handlers.py         # Handler tests
├── test_subjects.py         # Subject tests
├── test_middleware.py       # Middleware tests
├── test_flows.py            # Event flow tests
└── integration/
    └── test_full_flow.py    # Integration tests
```

### conftest.py

```python
import pytest
from krules_core.container import KRulesContainer

@pytest.fixture
def container():
    """Fresh container for each test"""
    return KRulesContainer()

@pytest.fixture
def handlers(container):
    """Handler decorators"""
    return container.handlers()
```

## Best Practices

1. **Isolate tests** - Fresh container per test
2. **Test handlers in isolation** - One handler per test
3. **Test event flows** - Verify cascades work correctly
4. **Mock external dependencies** - Don't call real APIs
5. **Use fixtures** - Share setup code
6. **Parametrize** - Test multiple scenarios
7. **Name clearly** - Test names describe what's tested
8. **Cleanup** - Clear Redis keys after tests
9. **Fast tests** - Use in-memory storage for unit tests
10. **Integration tests** - Separate from unit tests

## What's Next?

- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [API Reference](API_REFERENCE.md) - Complete API
