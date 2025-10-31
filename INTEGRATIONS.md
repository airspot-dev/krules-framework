# Integrations

KRules integrates with popular frameworks and services. This guide covers FastAPI, Google Cloud Pub/Sub, and CloudEvents.

## FastAPI Integration

The `krules_fastapi_env` module provides FastAPI integration with request-scoped containers.

### Installation

```bash
pip install "krules-framework[fastapi]"
```

### Basic Setup

```python
from fastapi import FastAPI
from krules_fastapi_env import KRulesApp

app = FastAPI()
krules = KRulesApp(app)

# Access container in routes
@app.get("/users/{user_id}")
async def get_user(user_id: str):
    user = krules.container.subject(f"user-{user_id}")
    return user.dict()
```

### With Handlers

```python
from fastapi import FastAPI
from krules_fastapi_env import KRulesApp

app = FastAPI()
krules = KRulesApp(app)

# Define handlers
on, when, middleware, emit = krules.container.handlers()

@on("user.created")
async def handle_user_created(ctx):
    ctx.subject.set("created_at", datetime.now().isoformat())

# API endpoint
@app.post("/users")
async def create_user(email: str, name: str):
    user = krules.container.subject(f"user-{uuid.uuid4()}")
    user.set("email", email)
    user.set("name", name)
    user.store()

    # Emit event
    on, when, middleware, emit = krules.container.handlers()
    await emit("user.created", user)

    return user.dict()
```

### Configuration

```python
from krules_fastapi_env import KRulesApp
from dependency_injector import providers
from redis_subjects_storage.storage_impl import create_redis_storage

app = FastAPI()
krules = KRulesApp(app)

# Configure Redis storage
redis_factory = create_redis_storage(
    url="redis://localhost:6379",
    key_prefix="api:"
)
krules.container.subject_storage.override(providers.Object(redis_factory))
```

For more details, see [krules_fastapi_env/README.md](krules_fastapi_env/README.md).

## Google Cloud Pub/Sub

The `krules_pubsub` and `krules_cloudevents_pubsub` modules provide Pub/Sub integration.

### Installation

```bash
pip install "krules-framework[pubsub]"
```

### Publishing Events

```python
from krules_cloudevents_pubsub import CloudEventsPubSubPublisher

# Create publisher
publisher = CloudEventsPubSubPublisher(
    project_id="my-project",
    topic_name="krules-events"
)

# Publish event as CloudEvent
user = container.subject("user-123")
await publisher.publish(
    event_type="user.created",
    subject=user,
    data={"timestamp": datetime.now().isoformat()}
)
```

### Subscribing to Events

```python
from krules_cloudevents_pubsub import CloudEventsPubSubSubscriber

# Create subscriber
subscriber = CloudEventsPubSubSubscriber(
    project_id="my-project",
    subscription_name="krules-subscription",
    container=container
)

# Define handlers (same as regular KRules handlers)
on, when, middleware, emit = container.handlers()

@on("user.created")
async def handle_user_created(ctx):
    print(f"Received user created: {ctx.subject.name}")

# Start subscriber
await subscriber.run()
```

For more details, see:
- [krules_pubsub/README.md](krules_pubsub/README.md)
- [krules_cloudevents_pubsub/README.md](krules_cloudevents_pubsub/README.md)

## CloudEvents

The `krules_cloudevents` module provides CloudEvents specification support.

### Installation

```bash
pip install "krules-framework[pubsub]"
```

### Creating CloudEvents

```python
from krules_cloudevents import CloudEvent

# Create CloudEvent
event = CloudEvent.create(
    type="com.example.user.created",
    source="/users/service",
    subject="user-123",
    data={"email": "john@example.com"}
)

# Access attributes
print(event.type)      # "com.example.user.created"
print(event.source)    # "/users/service"
print(event.subject)   # "user-123"
print(event.data)      # {"email": "john@example.com"}
```

### Parsing CloudEvents

```python
# Parse from JSON
json_data = '{"specversion": "1.0", "type": "user.created", ...}'
event = CloudEvent.from_json(json_data)
```

For more details, see [krules_cloudevents/README.md](krules_cloudevents/README.md).

## Custom Integrations

### Event Source Integration

Integrate custom event sources:

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

            # Emit as KRules event
            await self.emit(event_type, subject, json.loads(message.value))

# Use
kafka_source = KafkaEventSource(container, "krules-events")
await kafka_source.run()
```

### Event Sink Integration

Send events to external systems:

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
