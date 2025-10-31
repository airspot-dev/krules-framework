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
Tests for CloudEventsDispatcher (Publisher)
"""

import pytest
import json
import time
from krules_core.container import KRulesContainer
from krules_cloudevents_pubsub.publisher import CloudEventsDispatcher


@pytest.fixture
def container():
    """Create fresh KRules container."""
    return KRulesContainer()


@pytest.fixture
def dispatcher(container, pubsub_project):
    """Create CloudEventsDispatcher instance."""
    return CloudEventsDispatcher(
        project_id=pubsub_project,
        source="test-service",
        krules_container=container,
    )


class TestCloudEventsDispatcher:
    """Test suite for CloudEventsDispatcher (publisher)"""

    def test_dispatcher_initialization(self, dispatcher, pubsub_project):
        """Dispatcher should initialize with correct configuration."""
        assert dispatcher._project_id == pubsub_project
        assert dispatcher._source == "test-service"
        assert dispatcher._krules is not None
        assert dispatcher.default_dispatch_policy == "direct"

    def test_dispatch_publishes_to_topic(
        self, dispatcher, container, pubsub_topic, pubsub_subscription, subscriber_client
    ):
        """Dispatcher should publish CloudEvents to PubSub topic."""
        # Create subject
        subject = container.subject("test-subject-123")
        subject.set("test_prop", "test_value")

        # Dispatch event
        dispatcher.dispatch(
            event_type="test.event",
            subject=subject,
            payload={"key": "value", "number": 42},
            topic=pubsub_topic,
        )

        # Give PubSub time to propagate
        time.sleep(2)

        # Pull message from persistent subscription
        response = subscriber_client.pull(
            request={"subscription": pubsub_subscription, "max_messages": 10},
            timeout=5,
        )

        # Should have received 1 message
        assert len(response.received_messages) == 1

        message = response.received_messages[0].message

        # Verify CloudEvents attributes
        assert message.attributes["type"] == "test.event"
        assert message.attributes["source"] == "test-service"
        assert message.attributes["subject"] == "test-subject-123"
        assert "id" in message.attributes
        assert "time" in message.attributes

        # Verify payload
        payload = json.loads(message.data.decode())
        assert payload["key"] == "value"
        assert payload["number"] == 42

        # Ack message (cleanup handled by fixture)
        ack_ids = [msg.ack_id for msg in response.received_messages]
        subscriber_client.acknowledge(
            request={"subscription": pubsub_subscription, "ack_ids": ack_ids}
        )

    def test_dispatch_with_string_subject(
        self, dispatcher, container, pubsub_topic, pubsub_subscription, subscriber_client
    ):
        """Dispatcher should accept subject name as string."""
        # Dispatch with string subject
        dispatcher.dispatch(
            event_type="test.event",
            subject="string-subject",
            payload={"test": "data"},
            topic=pubsub_topic,
        )

        time.sleep(2)

        # Verify message published
        response = subscriber_client.pull(
            request={"subscription": pubsub_subscription, "max_messages": 10},
            timeout=5,
        )

        assert len(response.received_messages) == 1
        message = response.received_messages[0].message
        assert message.attributes["subject"] == "string-subject"

        # Ack message (cleanup handled by fixture)
        ack_ids = [msg.ack_id for msg in response.received_messages]
        subscriber_client.acknowledge(
            request={"subscription": pubsub_subscription, "ack_ids": ack_ids}
        )

    def test_dispatch_with_dataschema(
        self, dispatcher, container, pubsub_topic, pubsub_subscription, subscriber_client
    ):
        """Dispatcher should include dataschema in CloudEvent attributes."""
        subject = container.subject("test-subject")

        dispatcher.dispatch(
            event_type="order.created",
            subject=subject,
            payload={"amount": 100},
            topic=pubsub_topic,
            dataschema="https://example.com/schemas/order-v1",
        )

        time.sleep(2)

        response = subscriber_client.pull(
            request={"subscription": pubsub_subscription, "max_messages": 10},
            timeout=5,
        )

        assert len(response.received_messages) == 1
        message = response.received_messages[0].message
        assert message.attributes["dataschema"] == "https://example.com/schemas/order-v1"

        # Ack message (cleanup handled by fixture)
        ack_ids = [msg.ack_id for msg in response.received_messages]
        subscriber_client.acknowledge(
            request={"subscription": pubsub_subscription, "ack_ids": ack_ids}
        )

    def test_dispatch_without_topic_does_nothing(self, dispatcher, container):
        """Dispatcher should not publish if topic is None."""
        subject = container.subject("test-subject")

        # Should not raise, just return early
        dispatcher.dispatch(
            event_type="test.event",
            subject=subject,
            payload={"test": "data"},
            # No topic specified
        )

    def test_dispatch_includes_subject_ext_props(
        self, dispatcher, container, pubsub_topic, pubsub_subscription, subscriber_client
    ):
        """Dispatcher should include subject extended properties in message."""
        subject = container.subject("test-subject")
        subject.set_ext("routing_key", "orders.new")
        subject.set_ext("priority", "high")

        dispatcher.dispatch(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            topic=pubsub_topic,
        )

        time.sleep(2)

        response = subscriber_client.pull(
            request={"subscription": pubsub_subscription, "max_messages": 10},
            timeout=5,
        )

        assert len(response.received_messages) == 1
        message = response.received_messages[0].message

        # Extended properties should be in message attributes
        assert message.attributes["routing_key"] == "orders.new"
        assert message.attributes["priority"] == "high"

        # Ack message (cleanup handled by fixture)
        ack_ids = [msg.ack_id for msg in response.received_messages]
        subscriber_client.acknowledge(
            request={"subscription": pubsub_subscription, "ack_ids": ack_ids}
        )
