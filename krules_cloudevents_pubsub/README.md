# KRules CloudEvents PubSub Integration

Container-first publisher and subscriber for Google Cloud PubSub with CloudEvents format. Enables transparent event handling across services using KRules EventBus.

## Overview

This module provides two complementary components:

1. **Publisher (`CloudEventsDispatcher`)**: Sends events to PubSub topics in CloudEvents format
2. **Subscriber (`PubSubSubscriber`)**: Receives events from PubSub and routes them to local EventBus

Together, they enable **transparent cross-service event handling** where handlers registered with `@on()` work identically whether events are local or from external services.

## Key Concepts

### Transparent Event Flow

**Service A (Publisher)**:
```python
@on("order.created")
async def create_order(ctx: EventContext):
    # Validate order
    ctx.subject.set("status", "validated")

    # Emit to external topic - middleware handles publishing
    await ctx.emit("order.confirmed", ctx.subject, {...}, topic="orders")
```

**Service B (Subscriber)**:
```python
@on("order.confirmed")  # ← Same syntax, triggered by PubSub!
async def process_order(ctx: EventContext):
    # Same EventContext, same subject, same payload
    logger.info(f"Processing order: {ctx.subject.name}")
    ctx.subject.set("processed", True)
```

**No difference in handler syntax** - the flow is completely transparent.

---

## Publisher Setup

### 1. Container Configuration

Register the publisher in your application container using dependency injection:

```python
# In your_app/config/container.py
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import CloudEventsDispatcher
from krules_cloudevents_pubsub.middleware import create_dispatcher_middleware

def _register_dispatcher_middleware(event_bus, dispatcher):
    """
    Resource initializer for registering dispatcher middleware.

    Called automatically at container bootstrap.
    """
    middleware_func = create_dispatcher_middleware(dispatcher)
    event_bus.add_middleware(middleware_func)

    yield middleware_func


class Container(containers.DeclarativeContainer):
    """Application DI container."""

    __self__ = providers.Self()
    config = providers.Configuration()

    # ============ KRules Integration ============

    # KRules sub-container
    krules = providers.Container(
        KRulesContainer,
        config=config.krules
    )

    # ============ PubSub Publisher ============

    # CloudEvents dispatcher for publishing
    pubsub_publisher = providers.Singleton(
        CloudEventsDispatcher,
        project_id=config.project_id,
        source=config.service_name,  # e.g., "my-service.orders"
        krules_container=krules,
        topic_id=None,  # Topic specified per-event via 'topic' kwarg
        default_dispatch_policy="direct",  # DIRECT (external only) or BOTH (external + local)
    )

    # Register middleware (automatic lifecycle management)
    dispatcher_middleware = providers.Resource(
        _register_dispatcher_middleware,
        event_bus=krules.event_bus,
        dispatcher=pubsub_publisher,
    )
```

### 2. Application Initialization

```python
# In your_app/main.py
from .config.container import Container

# Create and initialize container
container = Container()
container.config.from_dict({
    "project_id": "my-gcp-project",
    "service_name": "order-service",
    "krules": {
        # KRules settings (storage, etc.)
    }
})

# Initialize resources (starts middleware)
container.init_resources()

# Get handlers
on, when, middleware, emit = container.krules.handlers()
```

### 3. Using the Publisher

The publisher works transparently via middleware - just add `topic` metadata:

```python
@on("order.created")
async def handle_order(ctx: EventContext):
    # Validate and process locally
    ctx.subject.set("status", "validated")

    # Publish to external topic
    await ctx.emit(
        "order.confirmed",
        ctx.subject,
        {"amount": 100.0, "currency": "USD"},
        topic="orders",  # ← Triggers external dispatch
    )
```

**Dispatch Policies**:

```python
# DIRECT (default) - external only, skip local handlers
await ctx.emit("alert.critical", topic="alerts")

# BOTH - external + local handlers
from krules_core.route.router import DispatchPolicyConst
await ctx.emit(
    "order.created",
    topic="orders",
    dispatch_policy=DispatchPolicyConst.BOTH
)
```

---

## Subscriber Setup

### 1. Container Configuration

Register the subscriber in your application container:

```python
# In your_app/config/container.py
import asyncio
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import PubSubSubscriber


def _start_subscriber(subscriber):
    """
    Resource initializer for PubSubSubscriber lifecycle.

    Starts the subscriber and manages its lifecycle.
    """
    # Start subscriber (will read SUBSCRIPTION_* env vars)
    task = asyncio.create_task(subscriber.start())

    yield subscriber

    # Cleanup on shutdown
    asyncio.create_task(subscriber.stop())


class Container(containers.DeclarativeContainer):
    """Application DI container."""

    __self__ = providers.Self()
    config = providers.Configuration()

    # ============ KRules Integration ============

    krules = providers.Container(
        KRulesContainer,
        config=config.krules
    )

    # ============ PubSub Subscriber ============

    # PubSub subscriber with injected KRules dependencies
    pubsub_subscriber = providers.Singleton(
        PubSubSubscriber,
        event_bus=krules.event_bus,
        subject_factory=krules.subject,
    )

    # Lifecycle management (start/stop)
    subscriber_lifecycle = providers.Resource(
        _start_subscriber,
        subscriber=pubsub_subscriber,
    )
```

### 2. Environment Configuration

The subscriber discovers subscriptions from environment variables:

```bash
# Format: SUBSCRIPTION_<NAME>=projects/<project>/subscriptions/<subscription>
export SUBSCRIPTION_ORDERS=projects/my-project/subscriptions/orders-sub
export SUBSCRIPTION_ALERTS=projects/my-project/subscriptions/alerts-sub
export SUBSCRIPTION_EVENTS=projects/my-project/subscriptions/events-sub
```

### 3. Application Initialization

```python
# In your_app/main.py
from .config.container import Container

# Create and initialize container
container = Container()
container.config.from_dict({
    "krules": {
        # KRules settings (storage, etc.)
    }
})

# Initialize resources (starts subscriber automatically)
container.init_resources()

# Get handlers
on, when, middleware, emit = container.krules.handlers()

# Register handlers - they'll be triggered by PubSub events!
@on("order.confirmed")
async def process_order(ctx: EventContext):
    logger.info(f"Received order: {ctx.subject.name}")
    ctx.subject.set("processed_at", datetime.now())
```

### 4. Handler Registration

Handlers work identically for local and PubSub events:

```python
@on("order.confirmed")
async def process_order(ctx: EventContext):
    """
    Triggered when:
    - Another service publishes "order.confirmed" to PubSub
    - Local code calls: await emit("order.confirmed", subject, payload)

    No difference in ctx.event_type, ctx.subject, ctx.payload!
    """
    logger.info(f"Processing order for: {ctx.subject.name}")

    # Access payload
    amount = ctx.payload.get("amount")
    currency = ctx.payload.get("currency")

    # Modify subject
    ctx.subject.set("status", "processing")
    ctx.subject.set("processed_at", datetime.now())

    # Emit follow-up events (local or external)
    await ctx.emit("order.processing", ctx.subject, {...})
```

---

## Full Example: Multi-Service Application

### Service A: Order Service (Publisher)

```python
# orders/config/container.py
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import CloudEventsDispatcher
from krules_cloudevents_pubsub.middleware import create_dispatcher_middleware


def _register_dispatcher_middleware(event_bus, dispatcher):
    middleware_func = create_dispatcher_middleware(dispatcher)
    event_bus.add_middleware(middleware_func)
    yield middleware_func


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    krules = providers.Container(KRulesContainer)

    pubsub_publisher = providers.Singleton(
        CloudEventsDispatcher,
        project_id="my-project",
        source="order-service",
        krules_container=krules,
    )

    dispatcher_middleware = providers.Resource(
        _register_dispatcher_middleware,
        event_bus=krules.event_bus,
        dispatcher=pubsub_publisher,
    )


# orders/main.py
from .config.container import Container

container = Container()
container.init_resources()

on, when, middleware, emit = container.krules.handlers()


@on("order.created")
async def create_order(ctx: EventContext):
    """Handle new order creation."""
    order_id = ctx.subject.name

    # Validate order
    if ctx.payload.get("amount") <= 0:
        await ctx.emit("order.rejected", ctx.subject, {"reason": "invalid_amount"})
        return

    # Save to database
    ctx.subject.set("status", "validated")
    ctx.subject.set("created_at", datetime.now())

    # Publish to other services via PubSub
    await ctx.emit(
        "order.confirmed",
        ctx.subject,
        {
            "amount": ctx.payload["amount"],
            "currency": ctx.payload.get("currency", "USD"),
        },
        topic="orders"  # ← Goes to PubSub
    )
```

### Service B: Payment Service (Subscriber)

```python
# payments/config/container.py
import asyncio
from dependency_injector import containers, providers
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import PubSubSubscriber


def _start_subscriber(subscriber):
    task = asyncio.create_task(subscriber.start())
    yield subscriber
    asyncio.create_task(subscriber.stop())


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    krules = providers.Container(KRulesContainer)

    pubsub_subscriber = providers.Singleton(
        PubSubSubscriber,
        event_bus=krules.event_bus,
        subject_factory=krules.subject,
    )

    subscriber_lifecycle = providers.Resource(
        _start_subscriber,
        subscriber=pubsub_subscriber,
    )


# payments/main.py
# Environment:
# SUBSCRIPTION_ORDERS=projects/my-project/subscriptions/orders-sub

from .config.container import Container

container = Container()
container.init_resources()  # Starts subscriber

on, when, middleware, emit = container.krules.handlers()


@on("order.confirmed")  # ← Triggered by PubSub from Order Service!
async def process_payment(ctx: EventContext):
    """Process payment for confirmed order."""
    order_id = ctx.subject.name
    amount = ctx.payload["amount"]
    currency = ctx.payload["currency"]

    logger.info(f"Processing payment for order {order_id}: {amount} {currency}")

    # Call payment gateway
    payment_result = await charge_payment(amount, currency)

    if payment_result.success:
        ctx.subject.set("payment_status", "completed")
        await ctx.emit("payment.completed", ctx.subject, {...})
    else:
        ctx.subject.set("payment_status", "failed")
        await ctx.emit("payment.failed", ctx.subject, {...})
```

---

## Advanced Usage

### Custom Lifecycle Management

For more control over subscriber lifecycle:

```python
from krules_cloudevents_pubsub import create_subscriber

async def main():
    # Get KRules dependencies
    container = Container()
    event_bus = container.krules.event_bus()
    subject_factory = container.krules.subject

    # Context manager for automatic cleanup
    async with create_subscriber(
        event_bus=event_bus,
        subject_factory=subject_factory,
    ) as subscriber:
        logger.info("Subscriber started")

        # Keep alive
        await asyncio.sleep(3600)

    # Subscriber automatically stopped on exit
```

### Manual Start/Stop

```python
subscriber = PubSubSubscriber(
    event_bus=container.krules.event_bus(),
    subject_factory=container.krules.subject,
)

await subscriber.start()

# ... do work ...

await subscriber.stop()
```

---

## Migration from Legacy Code

### Old (Legacy)

```python
# ❌ Legacy (deprecated)
from krules_core.providers import subject_factory, event_router_factory
from krules_pubsub.subscriber import PubSubSubscriber

subscriber = PubSubSubscriber()

handler = PubSubSubscriber.KRulesEventRouterHandler()
subscriber.add_process_function_for_subject(r"order-.*", handler)

await subscriber.start()
```

### New (Container-First)

```python
# ✅ Modern (KRules 2.0)
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub import PubSubSubscriber

container = KRulesContainer()

subscriber = PubSubSubscriber(
    event_bus=container.event_bus(),
    subject_factory=container.subject,
)

# No need to register handlers - they're already registered with @on()!
await subscriber.start()
```

### Import Path Changes

```python
# ❌ Old import (deprecated, backward compatible)
from krules_cloudevents_pubsub.route.dispatcher import CloudEventsDispatcher

# ✅ New import
from krules_cloudevents_pubsub.publisher import CloudEventsDispatcher

# Or use module-level import:
from krules_cloudevents_pubsub import CloudEventsDispatcher
```

---

## Testing

### Unit Testing with Mock Dependencies

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from krules_cloudevents_pubsub import PubSubSubscriber

@pytest.fixture
def mock_event_bus():
    bus = AsyncMock()
    bus.emit = AsyncMock()
    return bus

@pytest.fixture
def mock_subject_factory():
    def factory(name, **kwargs):
        subject = MagicMock()
        subject.name = name
        return subject
    return factory

@pytest.mark.asyncio
async def test_subscriber(mock_event_bus, mock_subject_factory):
    subscriber = PubSubSubscriber(
        event_bus=mock_event_bus,
        subject_factory=mock_subject_factory,
    )

    # Test subscriber logic...
    assert subscriber.event_bus is mock_event_bus
```

---

## Troubleshooting

### Subscriber not receiving messages

1. **Check environment variables**:
   ```bash
   env | grep SUBSCRIPTION_
   ```

2. **Verify GCP permissions**: Ensure service account has `pubsub.subscriber` role

3. **Check subscription exists**:
   ```bash
   gcloud pubsub subscriptions describe <subscription-name>
   ```

4. **Enable debug logging**:
   ```python
   import logging
   logging.getLogger("krules_cloudevents_pubsub").setLevel(logging.DEBUG)
   ```

### Events not publishing

1. **Verify middleware is registered**:
   ```python
   middlewares = container.krules.event_bus()._middlewares
   print(f"Registered middlewares: {len(middlewares)}")
   ```

2. **Check topic exists**:
   ```bash
   gcloud pubsub topics describe <topic-name>
   ```

3. **Verify 'topic' in emit() call**:
   ```python
   # ❌ Missing topic - won't publish
   await ctx.emit("order.created", ctx.subject, {...})

   # ✅ With topic - will publish
   await ctx.emit("order.created", ctx.subject, {...}, topic="orders")
   ```

---

## API Reference

### PubSubSubscriber

```python
class PubSubSubscriber:
    def __init__(
        self,
        event_bus,           # EventBus instance (required)
        subject_factory,     # Subject factory callable (required)
        logger=None          # Optional logger
    )

    async def start()       # Start subscriptions (reads SUBSCRIPTION_* env vars)
    async def stop()        # Stop all subscriptions and cleanup
```

### CloudEventsDispatcher

```python
class CloudEventsDispatcher:
    def __init__(
        self,
        project_id,                    # GCP project ID
        source,                        # CloudEvent source identifier
        krules_container,              # KRulesContainer instance
        topic_id=None,                 # Default topic (optional)
        batch_settings=(),             # PubSub batch settings
        publisher_options=(),          # PubSub publisher options
        publisher_kwargs={},           # Additional kwargs
        default_dispatch_policy="direct"  # "direct" or "both"
    )

    def dispatch(
        self,
        event_type,      # Event type string
        subject,         # Subject instance or name
        payload,         # Event payload dict
        **extra          # topic, dataschema, etc.
    )
```

---

## Further Reading

- [KRules Core Documentation](../krules_core/README.md)
- [CloudEvents Specification](https://cloudevents.io/)
- [Google Cloud PubSub Documentation](https://cloud.google.com/pubsub/docs)
- [Dependency Injector Documentation](https://python-dependency-injector.ets-labs.org/)

---

## License

Copyright 2019 The KRules Authors

Licensed under the Apache License, Version 2.0
