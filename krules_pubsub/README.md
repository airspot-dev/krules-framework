# KRules Pub/Sub

Base Google Cloud Pub/Sub integration for KRules Framework.

## Overview

This module provides base functionality for Google Cloud Pub/Sub integration. For complete CloudEvents support, see `krules_cloudevents_pubsub`.

## Features

- Publish messages to Pub/Sub topics
- Subscribe to Pub/Sub subscriptions
- Async-native implementation
- Error handling and retries

## Installation

```bash
pip install "krules-framework[pubsub]"
```

## Authentication

Set up Google Cloud credentials:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

Or use Application Default Credentials (ADC) in GCP environments.

## Usage

### Publisher

```python
from krules_pubsub import PubSubPublisher

# Create publisher
publisher = PubSubPublisher(
    project_id="my-project",
    topic_name="my-topic"
)

# Publish message
await publisher.publish(
    data=b'{"event": "user.created", "user_id": "123"}',
    attributes={"event_type": "user.created"}
)
```

### Subscriber

```python
from krules_pubsub import PubSubSubscriber

# Create subscriber
subscriber = PubSubSubscriber(
    project_id="my-project",
    subscription_name="my-subscription"
)

# Define message handler
async def handle_message(message):
    data = message.data.decode('utf-8')
    print(f"Received: {data}")
    message.ack()  # Acknowledge message

# Subscribe
await subscriber.subscribe(handle_message)
```

## CloudEvents Support

For CloudEvents format, use `krules_cloudevents_pubsub`:

```python
from krules_cloudevents_pubsub import CloudEventsPubSubPublisher

publisher = CloudEventsPubSubPublisher(
    project_id="my-project",
    topic_name="krules-events"
)

# Publish as CloudEvent
user = container.subject("user-123")
await publisher.publish(
    event_type="user.created",
    subject=user,
    data={"timestamp": datetime.now().isoformat()}
)
```

See [krules_cloudevents_pubsub](../krules_cloudevents_pubsub/README.md) for details.

## Configuration

### Publisher Configuration

```python
publisher = PubSubPublisher(
    project_id="my-project",
    topic_name="my-topic",
    # Optional:
    # timeout=60.0,  # Publish timeout in seconds
)
```

### Subscriber Configuration

```python
subscriber = PubSubSubscriber(
    project_id="my-project",
    subscription_name="my-subscription",
    # Optional:
    # max_messages=10,  # Max concurrent messages
    # timeout=300.0,    # Subscriber timeout
)
```

## Error Handling

### Publish Errors

```python
from google.api_core import exceptions

try:
    await publisher.publish(data=b"test")
except exceptions.GoogleAPIError as e:
    print(f"Publish failed: {e}")
```

### Subscriber Errors

```python
async def handle_message(message):
    try:
        process_message(message.data)
        message.ack()
    except Exception as e:
        print(f"Processing failed: {e}")
        message.nack()  # Negative acknowledge - will be redelivered
```

## Examples

### Simple Publisher

```python
import asyncio
from krules_pubsub import PubSubPublisher

async def main():
    publisher = PubSubPublisher(
        project_id="my-project",
        topic_name="events"
    )

    await publisher.publish(
        data=b'{"message": "Hello, Pub/Sub!"}',
        attributes={"source": "example"}
    )

if __name__ == "__main__":
    asyncio.run(main())
```

### Simple Subscriber

```python
import asyncio
import json
from krules_pubsub import PubSubSubscriber

async def handle_message(message):
    """Process received message"""
    data = json.loads(message.data.decode('utf-8'))
    print(f"Received: {data}")
    message.ack()

async def main():
    subscriber = PubSubSubscriber(
        project_id="my-project",
        subscription_name="my-subscription"
    )

    await subscriber.subscribe(handle_message)

if __name__ == "__main__":
    asyncio.run(main())
```

## Best Practices

1. **Idempotency** - Handle duplicate messages (Pub/Sub provides at-least-once delivery)
2. **Acknowledgment** - Always ack/nack messages
3. **Batch Publishing** - Publish multiple messages together when possible
4. **Error Handling** - Implement retry logic for transient errors
5. **Monitoring** - Monitor publish/subscribe metrics in GCP Console

## See Also

- [Integrations](../INTEGRATIONS.md) - Integration guide
- [krules_cloudevents_pubsub](../krules_cloudevents_pubsub/README.md) - CloudEvents integration
- [Google Cloud Pub/Sub Documentation](https://cloud.google.com/pubsub/docs)
