# Integrations

KRules integrates with external systems through two complementary mechanisms:

- **Event Receivers (Inbound)** - Bring external events INTO KRules for local processing
- **Event Emitters (Outbound)** - Send KRules events OUT to external systems

Both patterns enable KRules to participate in distributed event-driven architectures.

## Event Receivers (Inbound)

Event receivers expose KRules to external systems, allowing them to trigger local event handlers.

### FastAPI - HTTP CloudEvents Receiver

The `krules_fastapi_env` module creates an HTTP endpoint that receives CloudEvents and routes them to your local KRules handlers.

**What It Does:**
- Exposes HTTP endpoint that receives CloudEvents (POST `/krules`)
- Parses CloudEvents and extracts subject, event type, and payload
- Routes to local event bus, triggering matching handlers

**Installation:**

```bash
pip install "krules-framework[fastapi]"
```

**Example:**

```python
from krules_fastapi_env import KRulesApp
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Define local handlers (same as always)
@on("order.created")
async def handle_order(ctx):
    print(f"Received order: {ctx.subject.name}")
    await ctx.subject.set("status", "processing")

# Create FastAPI app that receives CloudEvents
app = KRulesApp(krules_container=container)

# Now external systems can POST CloudEvents to /krules endpoint:
# POST /krules
# Content-Type: application/cloudevents+json
# {
#   "specversion": "1.0",
#   "type": "order.created",
#   "source": "/external-system",
#   "subject": "order-123",
#   "data": {"amount": 100}
# }
```

**Use Case:** Microservice that receives HTTP CloudEvents from other services and processes them locally.

For more details, see [krules_fastapi_env/README.md](../krules_fastapi_env/README.md).

### Pub/Sub Subscriber - Pub/Sub Receiver

The `krules_cloudevents_pubsub` subscriber receives CloudEvents from Google Pub/Sub topics and routes them to local handlers.

**What It Does:**
- Subscribes to Google Pub/Sub subscription
- Receives CloudEvents from Pub/Sub topic
- Routes to local event bus, triggering matching handlers

**Installation:**

```bash
pip install "krules-framework[pubsub]"
```

**Example:**

```python
from krules_cloudevents_pubsub import PubSubSubscriber
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Define local handlers
@on("device.temperature-alert")
async def handle_alert(ctx):
    print(f"Alert from {ctx.subject.name}: {ctx.payload}")

# Subscribe to Pub/Sub topic
subscriber = PubSubSubscriber(
    project_id="my-project",
    subscription_name="krules-alerts",
    container=container
)

# Start receiving events from Pub/Sub
await subscriber.run()
```

**Use Case:** Service that listens to Pub/Sub topic and processes events published by other services.

For more details, see [krules_cloudevents_pubsub/README.md](../krules_cloudevents_pubsub/README.md).

## Event Emitters (Outbound)

Event emitters send KRules events to external systems. Both can be configured as **middleware** to transparently route all events, or used explicitly per event.

### HTTP CloudEvents - HTTP Emitter

The `krules_cloudevents` module sends CloudEvents to external HTTP endpoints.

**What It Does:**
- Converts KRules events to CloudEvents format
- Sends HTTP POST requests to external URLs
- Can be middleware (routes all events) or explicit (routes specific events)

**Installation:**

```bash
pip install "krules-framework[pubsub]"
```

**As Middleware (Transparent Routing):**

```python
from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Create dispatcher
dispatcher = CloudEventsDispatcher(
    dispatch_url="https://api.example.com/events",
    source="my-service",
    krules_container=container
)

# Register as middleware - ALL events are sent to external URL
dispatcher_mw = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(dispatcher_mw)

# Now all ctx.emit() calls also send to external URL
@on("order.created")
async def handle_order(ctx):
    # This emit triggers local handlers AND sends to external URL
    await ctx.emit("order.processing", ctx.subject, {"status": "processing"})
```

**Explicit Per-Event:**

```python
# Send specific event to external URL
await emit("user.created", user, dispatch_url="https://api.example.com/events")
```

**Use Case:** Notify external services about events happening in your KRules application.

For more details, see [krules_cloudevents/README.md](../krules_cloudevents/README.md).

### Pub/Sub Publisher - Pub/Sub Emitter

The `krules_cloudevents_pubsub` publisher sends CloudEvents to Google Pub/Sub topics.

**What It Does:**
- Converts KRules events to CloudEvents format
- Publishes to Google Pub/Sub topics
- Can be middleware (routes all events) or explicit (routes specific events)

**Installation:**

```bash
pip install "krules-framework[pubsub]"
```

**As Middleware (Transparent Routing):**

```python
from krules_cloudevents_pubsub import CloudEventsDispatcher, create_dispatcher_middleware
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Create dispatcher
dispatcher = CloudEventsDispatcher(
    project_id="my-project",
    default_topic="krules-events",
    source="my-service",
    krules_container=container
)

# Register as middleware - ALL events are published to Pub/Sub
dispatcher_mw = create_dispatcher_middleware(dispatcher)
container.event_bus().add_middleware(dispatcher_mw)

# Now all ctx.emit() calls also publish to Pub/Sub
@on("sensor.reading")
async def process_reading(ctx):
    # Emits locally AND publishes to Pub/Sub (via middleware)
    await ctx.emit("sensor.processed", ctx.subject, {"value": ctx.payload["value"]})
```

**Explicit Per-Event:**

```python
# Publish specific event to Pub/Sub topic
await emit("alert.critical", device, topic="critical-alerts")
```

**Use Case:** Publish events to Pub/Sub for consumption by other microservices.

For more details, see [krules_cloudevents_pubsub/README.md](../krules_cloudevents_pubsub/README.md).

## Complete Multi-Service Example

Here's how receivers and emitters work together in a distributed system:

```python
# SERVICE A: Receives HTTP CloudEvents, processes, publishes to Pub/Sub
from krules_fastapi_env import KRulesApp
from krules_cloudevents_pubsub import CloudEventsDispatcher, create_dispatcher_middleware
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Setup Pub/Sub emitter middleware
pubsub_dispatcher = CloudEventsDispatcher(
    project_id="my-project",
    default_topic="processed-events",
    source="service-a",
    krules_container=container
)
container.event_bus().add_middleware(create_dispatcher_middleware(pubsub_dispatcher))

# Define handler
@on("order.created")
async def process_order(ctx):
    await ctx.subject.set("status", "processing")
    # Emits locally AND publishes to Pub/Sub (via middleware)
    await ctx.emit("order.processed", ctx.subject)

# Expose HTTP receiver
app = KRulesApp(krules_container=container)
# External systems POST to /krules
```

```python
# SERVICE B: Subscribes to Pub/Sub, processes, sends HTTP CloudEvents
from krules_cloudevents_pubsub import PubSubSubscriber
from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware
from krules_core.container import KRulesContainer

container = KRulesContainer()
on, when, middleware, emit = container.handlers()

# Setup HTTP emitter middleware
http_dispatcher = CloudEventsDispatcher(
    dispatch_url="https://external-api.com/events",
    source="service-b",
    krules_container=container
)
container.event_bus().add_middleware(create_dispatcher_middleware(http_dispatcher))

# Define handler
@on("order.processed")
async def notify_fulfillment(ctx):
    await ctx.subject.set("notified", True)
    # Emits locally AND sends HTTP CloudEvent (via middleware)
    await ctx.emit("fulfillment.requested", ctx.subject)

# Subscribe to Pub/Sub
subscriber = PubSubSubscriber(
    project_id="my-project",
    subscription_name="service-b-sub",
    container=container
)
await subscriber.run()
```

**Flow:**
1. External system sends HTTP CloudEvent to Service A (`POST /krules`)
2. Service A receives, processes locally, and publishes to Pub/Sub
3. Service B subscribes to Pub/Sub, receives event, processes locally
4. Service B sends HTTP CloudEvent to external API

## Integration Summary

| Component | Direction | Middleware | Purpose |
|-----------|-----------|------------|---------|
| FastAPI | Inbound (Receiver) | N/A | Receive HTTP CloudEvents from external systems |
| Pub/Sub Subscriber | Inbound (Receiver) | N/A | Receive events from Pub/Sub topics |
| HTTP CloudEvents | Outbound (Emitter) | ✅ Yes | Send HTTP CloudEvents to external URLs |
| Pub/Sub Publisher | Outbound (Emitter) | ✅ Yes | Publish events to Pub/Sub topics |

## Custom Integrations

### Event Source Integration

Integrate custom event sources by routing them to the KRules event bus:

```python
class KafkaEventSource:
    """Integrate Kafka as event source"""

    def __init__(self, container, topic):
        self.container = container
        self.topic = topic
        self.consumer = KafkaConsumer(topic)
        on, when, middleware, self.emit = container.handlers()

    async def run(self):
        """Consume Kafka messages and emit as KRules events"""
        for message in self.consumer:
            # Parse message
            event_type = message.headers.get("event_type")
            subject_name = message.key.decode()

            # Get or create subject
            subject = self.container.subject(subject_name)

            # Emit as KRules event (triggers local handlers)
            await self.emit(event_type, subject, json.loads(message.value))

# Use
kafka_source = KafkaEventSource(container, "krules-events")
await kafka_source.run()
```

### Event Sink Integration

Send events to external systems using middleware:

```python
@middleware
async def webhook_sink(ctx, next):
    """Send all events to webhook"""
    await next()  # Execute handlers first

    # Send to webhook
    async with httpx.AsyncClient() as client:
        await client.post("https://webhook.example.com/events", json={
            "event_type": ctx.event_type,
            "subject": ctx.subject.name,
            "payload": ctx.payload,
            "timestamp": datetime.now().isoformat()
        })
```

## What's Next?

- [Advanced Patterns](ADVANCED_PATTERNS.md) - Production patterns
- [Testing](TESTING.md) - Testing strategies
- [API Reference](API_REFERENCE.md) - Complete API
