# KRules FastAPI Integration

FastAPI integration for KRules framework providing CloudEvents HTTP receiver endpoint.

## Overview

`krules_fastapi_env` provides `KrulesApp` - a FastAPI application pre-configured for KRules integration with:

- **CloudEvents HTTP Receiver**: POST endpoint that receives CloudEvents and emits them on EventBus
- **Container-First Pattern**: Receives `KRulesContainer` as dependency for clean IoC architecture
- **Subject Validation**: Strict validation requiring CloudEvent `subject` field

## Installation

```bash
uv add krules-fastapi-env
```

Or with pip:

```bash
pip install krules-fastapi-env
```

## Quick Start

### Basic Usage with Container IoC Pattern

```python
from contextlib import asynccontextmanager
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_fastapi_env import KrulesApp

# Application container with KRules sub-container
class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    krules = providers.Container(KRulesContainer, config=config.krules)

# Initialize container
container = AppContainer()

# Lifespan management (application responsibility)
@asynccontextmanager
async def lifespan(app):
    # Startup: initialize resources
    container.init_resources()

    # Register event handlers
    from my_app import handlers

    yield

    # Shutdown: cleanup
    container.krules().shutdown_resources()

# Create KrulesApp with injected krules container
app = KrulesApp(
    krules_container=container.krules,
    title="My KRules API",
    version="1.0.0",
    lifespan=lifespan
)
```

### KrulesApp as Container Provider (Recommended)

You can register `KrulesApp` directly as a provider in your IoC container:

```python
from contextlib import asynccontextmanager
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_fastapi_env import KrulesApp

class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()

    # KRules sub-container
    krules = providers.Container(KRulesContainer, config=config.krules)

    # Lifespan factory
    @staticmethod
    def lifespan_factory(container_instance):
        @asynccontextmanager
        async def lifespan(app):
            container_instance.init_resources()
            from my_app import handlers  # Register handlers
            yield
            container_instance.krules().shutdown_resources()
        return lifespan

    # KrulesApp as provider
    app = providers.Singleton(
        KrulesApp,
        krules_container=krules,
        title="My KRules API",
        version="1.0.0",
        lifespan=providers.Callable(lifespan_factory, container_instance=providers.Self())
    )

# Use the app
container = AppContainer()
app = container.app()
```

## CloudEvents HTTP Receiver

`KrulesApp` automatically registers a POST endpoint that receives CloudEvents via HTTP and emits them on the local EventBus.

### Endpoint Details

- **Path**: `/` (configurable via `cloudevents_path` parameter)
- **Method**: POST
- **Content-Type**: `application/json` (CloudEvents structured format)
- **Validation**: CloudEvent `subject` field is **required**

### Example Request

```bash
curl -X POST http://localhost:8000/ \
  -H "Content-Type: application/json" \
  -d '{
    "specversion": "1.0",
    "type": "order.created",
    "source": "orders-service",
    "id": "order-123",
    "subject": "order/123",
    "data": {
      "amount": 99.99,
      "status": "pending"
    }
  }'
```

### Response

```json
{"status": "accepted"}
```

### Custom Endpoint Path

```python
app = KrulesApp(
    krules_container=container.krules,
    cloudevents_path="/events"  # Custom path
)
```

## Event Handler Registration

Register event handlers using the `@on` decorator from `KRulesContainer`:

```python
from my_app.container import container

# Get handler decorators
on, when, middleware, emit = container.krules().handlers()

@on("order.created")
async def handle_order_created(ctx):
    """Handle order.created events"""
    subject = ctx.subject
    payload = ctx.payload

    # Process event
    subject.set("status", "processing")
    subject.set("amount", payload["amount"])
    subject.store()  # Persist changes

    # Emit follow-up event
    await emit("order.processing", subject, {"message": "Order processing started"})
```

## Subject Requirements

CloudEvents **must** include the `subject` field - this is required for KRules event routing.

### Valid CloudEvent

```json
{
  "specversion": "1.0",
  "type": "order.created",
  "source": "orders-service",
  "id": "order-123",
  "subject": "order/123",  ✅ Required
  "data": {"amount": 99.99}
}
```

### Invalid CloudEvent (Missing Subject)

```json
{
  "specversion": "1.0",
  "type": "order.created",
  "source": "orders-service",
  "id": "order-123",
  "data": {"amount": 99.99}
}
```

**Response**: `422 Unprocessable Entity`
```json
{
  "detail": "CloudEvent 'subject' field is required for KRules events"
}
```

## Configuration

### KrulesApp Parameters

```python
KrulesApp(
    krules_container: KRulesContainer,     # Required: KRules container instance
    cloudevents_path: str = "/",           # CloudEvents endpoint path
    *args, **kwargs                        # Passed to FastAPI.__init__
)
```

### FastAPI Parameters

All FastAPI parameters are supported:

```python
app = KrulesApp(
    krules_container=container.krules,
    title="My KRules API",
    version="1.0.0",
    description="API for processing KRules events",
    docs_url="/docs",
    redoc_url="/redoc"
)
```

## Lifespan Management

Lifespan management is the **application's responsibility**. This provides flexibility for custom initialization and cleanup.

### Best Practice Pattern

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Startup
    container.init_resources()

    # Register event handlers (CRITICAL: must be done after init_resources)
    from my_app import handlers

    # Optional: additional setup
    print("Application started")

    yield

    # Shutdown
    container.krules().shutdown_resources()
    print("Application shutdown")

app = KrulesApp(
    krules_container=container.krules,
    lifespan=lifespan
)
```

## Best Practices

### 1. Container-First Architecture

Always inject `KRulesContainer` into `KrulesApp`:

```python
# ✅ Good: Container IoC pattern
container = AppContainer()
app = KrulesApp(krules_container=container.krules)

# ❌ Bad: Direct instantiation
krules_container = KRulesContainer()
app = KrulesApp(krules_container=krules_container)
```

### 2. Register Handlers After init_resources()

```python
@asynccontextmanager
async def lifespan(app):
    container.init_resources()  # Initialize first
    from my_app import handlers  # Then register handlers
    yield
```

### 3. Explicit Subject Persistence

Subject changes are not automatically persisted. Call `.store()` explicitly:

```python
@on("order.created")
async def handle_order(ctx):
    subject = ctx.subject
    subject.set("status", "processing")
    subject.store()  # ✅ Explicit persistence
```

### 4. Subject Naming Conventions

Use clear, hierarchical subject names:

```python
# ✅ Good
"order/123"
"user/john.doe"
"inventory/product-456"

# ❌ Bad
"123"
"john"
"prod456"
```

### 5. Use Structured Payloads

Always use structured data in CloudEvent `data` field:

```python
# ✅ Good
{
  "type": "order.created",
  "subject": "order/123",
  "data": {
    "amount": 99.99,
    "currency": "USD",
    "items": [...]
  }
}

# ❌ Bad
{
  "type": "order.created",
  "subject": "order/123",
  "data": "order-details-string"
}
```

## Testing

Use `TestClient` from FastAPI for testing:

```python
import pytest
from fastapi.testclient import TestClient
from krules_core.container import KRulesContainer
from krules_fastapi_env import KrulesApp

@pytest.fixture
def krules_app():
    container = KRulesContainer()
    app = KrulesApp(
        krules_container=container,
        title="Test KRules API"
    )
    return app

def test_receive_cloudevent(krules_app):
    client = TestClient(krules_app)

    # Register event handler
    on, _, _, _ = krules_app._krules.handlers()

    emitted_events = []

    @on("test.event")
    async def capture_event(ctx):
        emitted_events.append({
            "type": ctx.event_type,
            "subject": ctx.subject.name,
            "payload": ctx.payload
        })

    # Send CloudEvent
    response = client.post("/", json={
        "specversion": "1.0",
        "type": "test.event",
        "source": "test-suite",
        "id": "test-123",
        "subject": "test-subject",
        "data": {"message": "hello"}
    })

    assert response.status_code == 200
    assert len(emitted_events) == 1
    assert emitted_events[0]["type"] == "test.event"
```

## API Reference

### KrulesApp

```python
class KrulesApp(FastAPI):
    """
    FastAPI application with KRules integration.

    Args:
        krules_container: KRulesContainer instance (required)
        cloudevents_path: CloudEvents receiver endpoint path (default: "/")
        *args, **kwargs: Passed to FastAPI.__init__
    """
```

### CloudEvents Endpoint

**POST {cloudevents_path}**

Receives CloudEvents via HTTP and emits them on the local EventBus.

**Request Body**: CloudEvent (JSON)
- `specversion` (string, required): CloudEvents version (e.g., "1.0")
- `type` (string, required): Event type (e.g., "order.created")
- `source` (string, required): Event source identifier
- `id` (string, required): Event ID
- `subject` (string, required): Subject name (KRules requirement)
- `data` (object, optional): Event payload

**Response**: 200 OK
```json
{"status": "accepted"}
```

**Error Response**: 422 Unprocessable Entity
```json
{
  "detail": "CloudEvent 'subject' field is required for KRules events"
}
```

## Comparison with PubSub Subscriber

`KrulesApp` CloudEvents endpoint is functionally equivalent to the PubSub subscriber:

| Feature | PubSub Subscriber | CloudEvents Endpoint |
|---------|-------------------|---------------------|
| Receives events | ✅ From PubSub topic | ✅ From HTTP POST |
| Emits on EventBus | ✅ Yes | ✅ Yes |
| Subject creation | ✅ From CloudEvent | ✅ From CloudEvent |
| Subject validation | ✅ Required | ✅ Required |
| Event routing | ✅ Via @on decorators | ✅ Via @on decorators |

## Examples

### Complete Application Example

```python
# app.py
from contextlib import asynccontextmanager
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_fastapi_env import KrulesApp

class AppContainer(containers.DeclarativeContainer):
    config = providers.Configuration()
    krules = providers.Container(KRulesContainer, config=config.krules)

container = AppContainer()

@asynccontextmanager
async def lifespan(app):
    container.init_resources()
    from . import handlers  # Register handlers
    yield
    container.krules().shutdown_resources()

app = KrulesApp(
    krules_container=container.krules,
    title="Orders API",
    version="1.0.0",
    lifespan=lifespan
)
```

```python
# handlers.py
from app import container

on, when, middleware, emit = container.krules().handlers()

@on("order.created")
async def handle_order_created(ctx):
    subject = ctx.subject
    payload = ctx.payload

    # Set subject properties
    subject.set("status", "processing")
    subject.set("amount", payload["amount"])
    subject.set("created_at", payload.get("created_at"))
    subject.store()

    # Emit follow-up event
    await emit("order.processing", subject, {
        "message": "Order processing started",
        "order_id": subject.name
    })

@on("order.processing")
async def handle_order_processing(ctx):
    subject = ctx.subject

    # Business logic
    amount = subject.get("amount")

    if amount > 100:
        subject.set("priority", "high")
    else:
        subject.set("priority", "normal")

    subject.set("status", "completed")
    subject.store()

    await emit("order.completed", subject, {
        "priority": subject.get("priority")
    })
```

```bash
# Run with uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## License

Apache License 2.0
