# KRules CloudEvents HTTP Integration

Provides HTTP dispatcher for sending events to external endpoints using CloudEvents format.
Enables transparent event handling across services via middleware integration with KRules EventBus.

## Overview

This module allows KRules applications to send events to external HTTP endpoints using the CloudEvents specification (binary mode). Events can be dispatched transparently using middleware, making remote service communication as simple as local event handling.

### Key Features

- **CloudEvents v1.x** - Modern CloudEvents specification with Pydantic models
- **Container-first DI** - Integrates seamlessly with KRulesContainer
- **Transparent dispatch** - Use `ctx.emit(..., dispatch_url="...")` for external events
- **Middleware integration** - Automatic dispatch via EventBus middleware
- **Flexible dispatch policies** - Control whether local handlers run (DIRECT vs BOTH)
- **Dynamic URLs** - Support for callable dispatch URLs based on event type
- **Async-ready** - Uses httpx for async HTTP requests
- **Extended properties** - Preserves subject metadata as CloudEvent attributes
- **Event chain tracking** - Preserves originid for event tracing

## Installation

```bash
# Already included in krules-framework
pip install krules-framework
```

## Quick Start

### Publisher Setup

```python
from krules_core.container import KRulesContainer
from krules_cloudevents import (
    CloudEventsDispatcher,
    create_dispatcher_middleware,
    DispatchPolicyConst,
)

# Create container
container = KRulesContainer()

# Create dispatcher
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://api.example.com/events",  # or callable
    source="order-service",
    krules_container=container,
)

# Register middleware for transparent emit()
middleware_func = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(middleware_func)

# Get handlers
on, when, middleware, emit = container.handlers()
```

### Transparent Event Dispatch

```python
@on("order.created")
async def handle_order(ctx: EventContext):
    # Process order locally
    ctx.subject.set("status", "validated")

    # Send notification to external service (DIRECT - external only)
    await ctx.emit(
        "notification.send",
        {"type": "email", "template": "order_confirmation"},
        ctx.subject,
        dispatch_url="https://notification-service.example.com/send",
    )

    # Or dispatch AND execute local handlers (BOTH policy)
    await ctx.emit(
        "audit.log",
        {"action": "order_created"},
        ctx.subject,
        dispatch_url="https://audit-service.example.com/log",
        dispatch_policy=DispatchPolicyConst.BOTH,
    )

# Emit event (triggers handler)
subject = container.subject("order-123")
await emit("order.created", subject, {"amount": 100.0})
```

### Direct Dispatch (No Middleware)

```python
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://api.example.com/events",
    source="order-service",
    krules_container=container,
)

# Direct dispatch
subject = container.subject("order-456")
event_id = dispatcher.dispatch(
    event_type="order.created",
    subject=subject,
    payload={"amount": 200.0},
    dispatch_url="https://override.example.com/events",  # Override default
)
```

## Dispatch Policies

Control whether events dispatched to external URLs also trigger local handlers:

### DIRECT (default)
Dispatch to external URL **only**, skip local handlers.

```python
await ctx.emit(
    "notification.send",
    payload,
    subject,
    dispatch_url="https://...",
    # No dispatch_policy = DIRECT (default)
)
```

### BOTH
Dispatch to external URL **and** execute local handlers.

```python
await ctx.emit(
    "audit.log",
    payload,
    subject,
    dispatch_url="https://...",
    dispatch_policy=DispatchPolicyConst.BOTH,
)
```

## Dynamic Dispatch URLs

Use a callable to determine dispatch URL based on event type:

```python
def get_dispatch_url(subject, event_type):
    if event_type.startswith("order."):
        return "https://order-service.example.com/events"
    elif event_type.startswith("payment."):
        return "https://payment-service.example.com/events"
    return "https://api.example.com/events"

dispatcher = CloudEventsDispatcher(
    dispatch_url=get_dispatch_url,  # Callable
    source="gateway-service",
    krules_container=container,
)
```

## CloudEvents Format

Events are sent in CloudEvents **binary mode** (headers + body):

### Request Headers
```
ce-id: a1b2c3d4-5678-90ab-cdef-1234567890ab
ce-type: order.created
ce-source: order-service
ce-subject: order-123
ce-time: 2025-10-31T12:00:00.000000+00:00
ce-originid: root-event-id  # For event chain tracking
ce-tenant_id: tenant-abc    # Extended properties
content-type: application/json
```

### Request Body
```json
{
  "amount": 100.0,
  "currency": "USD"
}
```

## Extended Properties

Subject extended properties are included as CloudEvent attributes:

```python
subject = container.subject("tenant-resource")
subject.set_ext("tenant_id", "tenant-abc")
subject.set_ext("environment", "production")

dispatcher.dispatch(
    event_type="resource.updated",
    subject=subject,
    payload={"changes": ["field1"]},
)

# Result: ce-tenant_id and ce-environment headers
```

## Event Chain Tracking

The `originid` attribute tracks event chains across services:

```python
# Service A: Original event
subject = container.subject("order-123")
await emit("order.created", subject, {"amount": 100})
# originid = <event-id>

# Service B: Receives event, emits new event
@on("order.created")
async def handle_order(ctx: EventContext):
    # ctx.subject preserves event_info with originid
    await ctx.emit("payment.process", payload, ctx.subject)
    # originid = <original-event-id>  # Preserved!
```

**Note**: `event_info` currently resides in Subject but should be moved to event context. See TODO in code.

## Multi-Service Example

### Service A: Order Service
```python
# Setup
container = KRulesContainer()
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://payment-service.example.com/events",
    source="order-service",
    krules_container=container,
)
middleware_func = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(middleware_func)
on, when, middleware, emit = container.handlers()

# Handler
@on("order.placed")
async def process_order(ctx: EventContext):
    ctx.subject.set("status", "validated")

    # Request payment from payment service
    await ctx.emit(
        "payment.process",
        {"amount": ctx.payload["total"]},
        ctx.subject,
        dispatch_url="https://payment-service.example.com/events",
    )

# Emit
subject = container.subject("order-789")
await emit("order.placed", subject, {"total": 500.0})
```

### Service B: Payment Service
Receives CloudEvent HTTP POST at `https://payment-service.example.com/events`:

```python
from flask import Flask, request
from cloudevents.pydantic import CloudEvent
import json

app = Flask(__name__)

@app.route("/events", methods=["POST"])
def handle_event():
    # Parse CloudEvent from binary format
    attributes = {}
    for header, value in request.headers:
        if header.lower().startswith("ce-"):
            key = header[3:]  # Remove 'ce-' prefix
            attributes[key] = value

    event_type = attributes["type"]
    subject_name = attributes["subject"]
    payload = request.json

    # Process event
    if event_type == "payment.process":
        process_payment(subject_name, payload["amount"])

    return {"status": "ok"}, 200
```

Or use KRules in Service B too for symmetric handling:

```python
# Service B can also use KRules EventBus to handle incoming CloudEvents
# by implementing a CloudEvents → EventBus bridge (future feature)
```

## Migration from Legacy

### Legacy (krules_core.providers)
```python
from krules_core.providers import subject_factory
from krules_core.route.dispatcher import CloudEventsDispatcher

dispatcher = CloudEventsDispatcher(
    dispatch_url="https://...",
    source="order-service",
)

subject = subject_factory("order-123")
dispatcher.dispatch("order.created", subject, {"amount": 100})
```

### Modern (Container-first)
```python
from krules_core.container import KRulesContainer
from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware

container = KRulesContainer()
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://...",
    source="order-service",
    krules_container=container,
)

# Option A: Middleware (transparent)
middleware_func = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(middleware_func)

on, when, middleware, emit = container.handlers()
subject = container.subject("order-123")
await emit("order.created", subject, {"amount": 100}, dispatch_url="https://...")

# Option B: Direct dispatch
subject = container.subject("order-123")
dispatcher.dispatch("order.created", subject, {"amount": 100})
```

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────┐
│ KRules Application (Service A)                  │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │ EventBus                                   │  │
│  │  ┌──────────────────────────────────────┐ │  │
│  │  │ Middleware Stack                     │ │  │
│  │  │  - CloudEventsDispatcherMiddleware   │ │  │
│  │  └──────────────────────────────────────┘ │  │
│  │  ┌──────────────────────────────────────┐ │  │
│  │  │ Handlers                              │ │  │
│  │  │  @on("order.created")                 │ │  │
│  │  └──────────────────────────────────────┘ │  │
│  └───────────────────────────────────────────┘  │
│                                                  │
│  ┌───────────────────────────────────────────┐  │
│  │ CloudEventsDispatcher                     │  │
│  │  - dispatch_url                           │  │
│  │  - source                                  │  │
│  │  - default_dispatch_policy                 │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
                     │ HTTP POST
                     │ CloudEvents Binary
                     ▼
┌─────────────────────────────────────────────────┐
│ External Service (Service B)                    │
│  - Receives CloudEvent via HTTP                 │
│  - Processes event                              │
│  - Returns response                             │
└─────────────────────────────────────────────────┘
```

### Event Flow

1. **emit() with dispatch_url** → Creates EventContext with metadata
2. **EventBus** → Finds matching handlers
3. **Middleware** → Checks for `dispatch_url` in metadata
4. **Dispatcher** → Sends HTTP POST with CloudEvents binary format
5. **Policy check**:
   - **DIRECT**: Skip local handlers (no `next()`)
   - **BOTH**: Execute local handlers (`next()`)

## Configuration

### Dispatcher Options

```python
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://...",        # Required: Target URL or callable
    source="order-service",             # Required: CloudEvent source
    krules_container=container,         # Required: Container instance
    default_dispatch_policy="direct",   # Optional: Default policy for middleware
    test=False,                         # Optional: Enable test mode (returns extended info)
)
```

### Test Mode

For testing, enable test mode to get extended response info:

```python
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://...",
    source="test-service",
    krules_container=container,
    test=True,  # Enable test mode
)

event_id, status_code, headers = dispatcher.dispatch(
    event_type="test.event",
    subject=subject,
    payload={"data": "test"},
)

assert status_code == 200
assert "ce-id" in headers
```

## Troubleshooting

### Dispatch not happening

**Problem**: Events with `dispatch_url` are not being dispatched externally.

**Solution**: Ensure middleware is registered BEFORE handlers:

```python
# 1. Create dispatcher
dispatcher = CloudEventsDispatcher(...)

# 2. Register middleware
middleware_func = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(middleware_func)

# 3. Define handlers (AFTER middleware registration)
on, when, middleware, emit = container.handlers()

@on("order.created")
async def handle_order(ctx):
    await ctx.emit("notification", ..., dispatch_url="https://...")
```

### Middleware only runs with handlers

**Problem**: Dispatch doesn't happen when there are no handlers for the event type.

**Explanation**: EventBus middleware only runs when there are matching handlers. This is by design.

**Solution**: Register a no-op handler if you only want external dispatch:

```python
@on("notification.send")
async def notification_handler(ctx):
    pass  # No local processing, only external dispatch
```

### HTTP errors not failing

**Problem**: HTTP errors don't stop execution.

**Explanation**: By default, dispatch errors are logged but don't raise exceptions to allow local handlers to continue.

**Solution**: For DIRECT policy, errors DO raise. For BOTH policy, check metadata:

```python
@on("order.created")
async def handle_order(ctx):
    await ctx.emit("notification", ..., dispatch_url="https://...")

    if ctx.get_metadata("_dispatch_error"):
        # Handle dispatch failure
        logger.error(f"Dispatch failed: {ctx.get_metadata('_dispatch_error')}")
```

## API Reference

### CloudEventsDispatcher

#### `__init__(dispatch_url, source, krules_container, default_dispatch_policy="direct", test=False)`

Initialize dispatcher with container DI.

- **dispatch_url** (str | callable): Target URL or `callable(subject, event_type) -> URL`
- **source** (str): CloudEvent source identifier
- **krules_container** (KRulesContainer): Container instance
- **default_dispatch_policy** (str): Default policy for middleware ("direct" or "both")
- **test** (bool): Enable test mode (returns extended info)

#### `dispatch(event_type, subject, payload, **extra)`

Dispatch event to external HTTP endpoint.

- **event_type** (str): Event type (e.g., "order.created")
- **subject** (Subject | str): Subject instance or name
- **payload** (dict): Event data
- **extra**: Additional kwargs (dispatch_url, propertyname, etc.)

**Returns**: Event ID (str) or tuple(id, status, headers) if test=True

### Middleware

#### `create_dispatcher_middleware(dispatcher)`

Create middleware function for EventBus.

- **dispatcher** (CloudEventsDispatcher): Dispatcher instance

**Returns**: Middleware function

### Dispatch Policy

#### `DispatchPolicyConst`

- **DIRECT**: Dispatch externally, skip local handlers
- **BOTH**: Dispatch externally AND execute local handlers
- **NEVER** (deprecated): Skip dispatch
- **DEFAULT** (deprecated): Use DIRECT
- **ALWAYS** (deprecated): Use BOTH

## Related Modules

- **krules_cloudevents_pubsub**: CloudEvents over Google Cloud PubSub
- **krules_core**: Core EventBus and container
- **krules_fastapi_env**: FastAPI integration for receiving CloudEvents

## License

Apache License 2.0
