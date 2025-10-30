# Copyright 2019 The KRules Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Tests for PubSubSubscriber
"""

import pytest
import json
import asyncio
from krules_core.container import KRulesContainer
from krules_core import EventContext
from krules_cloudevents_pubsub.subscriber import PubSubSubscriber


@pytest.fixture
def container():
    """Create fresh KRules container."""
    return KRulesContainer()


@pytest.fixture
def subscriber(container):
    """Create PubSubSubscriber instance."""
    return PubSubSubscriber(
        event_bus=container.event_bus(),
        subject_factory=container.subject,
    )


class TestPubSubSubscriber:
    """Test suite for PubSubSubscriber"""

    def test_subscriber_initialization(self, subscriber, container):
        """Subscriber should initialize with injected dependencies."""
        assert subscriber.event_bus is not None
        assert subscriber.subject_factory is not None
        assert subscriber._running is False
        assert len(subscriber.subscription_tasks) == 0

    def test_subscriber_requires_event_bus(self, container):
        """Subscriber should raise if event_bus is None."""
        with pytest.raises(ValueError, match="event_bus is required"):
            PubSubSubscriber(
                event_bus=None,
                subject_factory=container.subject,
            )

    def test_subscriber_requires_subject_factory(self, container):
        """Subscriber should raise if subject_factory is None."""
        with pytest.raises(ValueError, match="subject_factory is required"):
            PubSubSubscriber(
                event_bus=container.event_bus(),
                subject_factory=None,
            )

    @pytest.mark.asyncio
    async def test_subscriber_triggers_handlers(
        self, container, subscriber, publisher_client, pubsub_topic, pubsub_subscription
    ):
        """Subscriber should trigger registered @on handlers when receiving PubSub messages."""
        on, when, middleware, emit = container.handlers()

        # Track handler calls
        received_events = []

        @on("order.created")
        async def handle_order(ctx: EventContext):
            received_events.append({
                "event_type": ctx.event_type,
                "subject_name": ctx.subject.name,
                "payload": ctx.payload,
            })

        # Set environment variable for subscription
        import os
        os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription

        # Start subscriber in background
        subscriber_task = asyncio.create_task(subscriber.start())

        # Give subscriber time to connect
        await asyncio.sleep(2)

        # Publish test message
        message_data = json.dumps({"amount": 100, "currency": "USD"}).encode()
        future = publisher_client.publish(
            pubsub_topic,
            message_data,
            type="order.created",
            source="test-publisher",
            subject="order-123",
        )
        future.result(timeout=10)

        # Give subscriber time to process
        await asyncio.sleep(2)

        # Verify handler was called
        assert len(received_events) == 1
        event = received_events[0]
        assert event["event_type"] == "order.created"
        assert event["subject_name"] == "order-123"
        assert event["payload"]["amount"] == 100
        assert event["payload"]["currency"] == "USD"

        # Cleanup
        await subscriber.stop()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        # Clean env var
        del os.environ["SUBSCRIPTION_TEST"]

    @pytest.mark.asyncio
    async def test_subscriber_with_no_subscriptions(self, subscriber):
        """Subscriber should handle no SUBSCRIPTION_* env vars gracefully."""
        import os

        # Ensure no SUBSCRIPTION_* vars exist
        for key in list(os.environ.keys()):
            if key.startswith("SUBSCRIPTION_"):
                del os.environ[key]

        # Should start without error
        await subscriber.start()

        # Should have no subscription tasks
        assert len(subscriber.subscription_tasks) == 0
        assert subscriber._running is True

        await subscriber.stop()

    @pytest.mark.asyncio
    async def test_subscriber_processes_multiple_messages(
        self, container, subscriber, publisher_client, pubsub_topic, pubsub_subscription
    ):
        """Subscriber should process multiple messages in sequence."""
        on, when, middleware, emit = container.handlers()

        # Track handler calls
        received_events = []

        @on("test.event")
        async def handle_test(ctx: EventContext):
            received_events.append(ctx.payload["sequence"])

        import os
        os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription

        subscriber_task = asyncio.create_task(subscriber.start())
        await asyncio.sleep(2)

        # Publish 3 messages
        for i in range(3):
            message_data = json.dumps({"sequence": i}).encode()
            future = publisher_client.publish(
                pubsub_topic,
                message_data,
                type="test.event",
                source="test",
                subject="test-subject",
            )
            future.result(timeout=10)

        # Give subscriber time to process all messages
        await asyncio.sleep(3)

        # All messages should be processed
        assert len(received_events) == 3
        assert set(received_events) == {0, 1, 2}

        # Cleanup
        await subscriber.stop()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        del os.environ["SUBSCRIPTION_TEST"]

    @pytest.mark.asyncio
    async def test_subscriber_creates_subjects_with_factory(
        self, container, subscriber, publisher_client, pubsub_topic, pubsub_subscription
    ):
        """Subscriber should create subjects using injected factory."""
        on, when, middleware, emit = container.handlers()

        # Track created subjects
        subjects = []

        @on("test.event")
        async def handle_test(ctx: EventContext):
            subjects.append(ctx.subject)
            # Verify it's a real Subject instance with storage
            assert hasattr(ctx.subject, "_storage")
            assert hasattr(ctx.subject, "set")
            assert hasattr(ctx.subject, "get")

        import os
        os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription

        subscriber_task = asyncio.create_task(subscriber.start())
        await asyncio.sleep(2)

        # Publish message
        message_data = json.dumps({"test": "data"}).encode()
        future = publisher_client.publish(
            pubsub_topic,
            message_data,
            type="test.event",
            source="test",
            subject="my-subject",
        )
        future.result(timeout=10)

        await asyncio.sleep(2)

        # Subject should be created
        assert len(subjects) == 1
        assert subjects[0].name == "my-subject"

        # Cleanup
        await subscriber.stop()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        del os.environ["SUBSCRIPTION_TEST"]

    @pytest.mark.asyncio
    async def test_subscriber_stop_cleanup(self, subscriber):
        """Subscriber.stop() should clean up all resources."""
        import os
        os.environ["SUBSCRIPTION_FAKE"] = "projects/test/subscriptions/fake"

        # Start subscriber
        await subscriber.start()
        assert subscriber._running is True

        # Stop subscriber
        await subscriber.stop()
        assert subscriber._running is False

        # Clean env
        del os.environ["SUBSCRIPTION_FAKE"]
