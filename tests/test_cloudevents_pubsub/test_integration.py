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
Integration tests for Publisher + Subscriber end-to-end flow
"""

import pytest
import os
import asyncio
from krules_core.container import KRulesContainer
from krules_core import EventContext
from krules_cloudevents_pubsub import (
    CloudEventsDispatcher,
    PubSubSubscriber,
    create_dispatcher_middleware,
    DispatchPolicyConst,
)


@pytest.fixture
def publisher_container(pubsub_project, pubsub_topic):
    """Create container for publisher service."""
    container = KRulesContainer()

    # Create dispatcher
    dispatcher = CloudEventsDispatcher(
        project_id=pubsub_project,
        source="publisher-service",
        krules_container=container,
    )

    # Register middleware
    middleware_func = create_dispatcher_middleware(dispatcher)
    container.event_bus().add_middleware(middleware_func)

    return container


@pytest.fixture
def subscriber_container():
    """Create container for subscriber service."""
    return KRulesContainer()


@pytest.fixture
def subscriber_instance(subscriber_container):
    """Create subscriber instance."""
    return PubSubSubscriber(
        event_bus=subscriber_container.event_bus(),
        subject_factory=subscriber_container.subject,
    )


class TestPublisherSubscriberIntegration:
    """Integration tests for publisher/subscriber flow"""

    @pytest.mark.asyncio
    async def test_end_to_end_event_flow(
        self,
        publisher_container,
        subscriber_container,
        subscriber_instance,
        pubsub_topic,
        pubsub_subscription,
    ):
        """
        Test complete flow: emit() with topic → PubSub → subscriber → @on handler
        """
        # Setup publisher handlers
        pub_on, pub_when, pub_middleware, pub_emit = publisher_container.handlers()

        # Register no-op handler on publisher side (required for middleware to run)
        @pub_on("order.confirmed")
        async def noop_handler(ctx: EventContext):
            """No-op handler - only external dispatch, no local processing"""
            pass

        # Setup subscriber handlers
        sub_on, sub_when, sub_middleware, sub_emit = subscriber_container.handlers()

        # Track events in subscriber
        received_events = []

        @sub_on("order.confirmed")
        async def handle_order_confirmed(ctx: EventContext):
            received_events.append({
                "event_type": ctx.event_type,
                "subject_name": ctx.subject.name,
                "amount": ctx.payload.get("amount"),
                "currency": ctx.payload.get("currency"),
            })

        # Configure subscriber
        os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription
        subscriber_task = asyncio.create_task(subscriber_instance.start())
        await asyncio.sleep(2)

        # Publisher emits event with topic (triggers middleware → PubSub)
        publisher_subject = publisher_container.subject("order-456")
        await pub_emit(
            "order.confirmed",
            publisher_subject,
            {"amount": 250.0, "currency": "EUR"},
            topic=pubsub_topic,
        )

        # Give time for: publisher → PubSub → subscriber → handler
        await asyncio.sleep(3)

        # Verify subscriber received and processed the event
        assert len(received_events) == 1

        event = received_events[0]
        assert event["event_type"] == "order.confirmed"
        assert event["subject_name"] == "order-456"
        assert event["amount"] == 250.0
        assert event["currency"] == "EUR"

        # Cleanup
        await subscriber_instance.stop()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        del os.environ["SUBSCRIPTION_TEST"]

    @pytest.mark.asyncio
    async def test_transparent_event_handling(
        self,
        publisher_container,
        subscriber_container,
        subscriber_instance,
        pubsub_topic,
        pubsub_subscription,
    ):
        """
        Test that handler syntax is identical for local and remote events.

        Publisher service creates order → subscriber service processes it.
        """
        # Publisher: Order creation service
        pub_on, pub_when, pub_middleware, pub_emit = publisher_container.handlers()

        # Register no-op handler for order.confirmed (required for middleware to run)
        @pub_on("order.confirmed")
        async def noop_handler(ctx: EventContext):
            """No-op handler - only external dispatch"""
            pass

        # Subscriber: Payment processing service
        sub_on, sub_when, sub_middleware, sub_emit = subscriber_container.handlers()

        # Track payment processing
        processed_orders = []

        @sub_on("order.confirmed")
        async def process_payment(ctx: EventContext):
            """Payment service processes confirmed orders."""
            order_id = ctx.subject.name
            amount = ctx.payload["amount"]

            # Simulate payment processing
            await ctx.subject.set("payment_status", "processing")

            processed_orders.append({
                "order_id": order_id,
                "amount": amount,
            })

        # Start subscriber
        os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription
        subscriber_task = asyncio.create_task(subscriber_instance.start())
        await asyncio.sleep(2)

        # Publisher: Create and confirm order
        @pub_on("order.created")
        async def create_order(ctx: EventContext):
            """Order service creates order and publishes confirmation."""
            # Validate order
            await ctx.subject.set("status", "validated")

            # Publish confirmation to payment service
            await ctx.emit(
                "order.confirmed",
                {
                    "amount": ctx.payload["amount"],
                    "currency": "USD",
                },
                ctx.subject,
                topic=pubsub_topic,  # ← Goes to external service
            )

        # Trigger order creation
        order_subject = publisher_container.subject("order-789")
        await pub_emit(
            "order.created",
            order_subject,
            {"amount": 500.0},
        )

        # Give time for full flow
        await asyncio.sleep(3)

        # Verify payment service processed the order
        assert len(processed_orders) == 1
        assert processed_orders[0]["order_id"] == "order-789"
        assert processed_orders[0]["amount"] == 500.0

        # Cleanup
        await subscriber_instance.stop()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        del os.environ["SUBSCRIPTION_TEST"]

    @pytest.mark.asyncio
    async def test_subject_state_preserved_across_services(
        self,
        publisher_container,
        subscriber_container,
        subscriber_instance,
        pubsub_topic,
        pubsub_subscription,
    ):
        """
        Test that subject name is preserved across services.

        Note: Subject state (properties) is NOT shared - each service has
        its own storage. Only the subject name and event payload are shared.
        """
        pub_on, pub_when, pub_middleware, pub_emit = publisher_container.handlers()

        # Register no-op handler (required for middleware to run)
        @pub_on("test.event")
        async def noop_handler(ctx: EventContext):
            """No-op handler - only external dispatch"""
            pass

        sub_on, sub_when, sub_middleware, sub_emit = subscriber_container.handlers()

        # Track subjects in subscriber
        subjects_received = []

        @sub_on("test.event")
        async def handle_test(ctx: EventContext):
            subjects_received.append({
                "name": ctx.subject.name,
                "payload": ctx.payload,
            })

        # Start subscriber
        os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription
        subscriber_task = asyncio.create_task(subscriber_instance.start())
        await asyncio.sleep(2)

        # Publisher emits event for specific subject
        subject = publisher_container.subject("device-sensor-42")
        await subject.set("local_prop", "not_transmitted")  # Local only

        await pub_emit(
            "test.event",
            subject,
            {"temperature": 23.5, "unit": "celsius"},
            topic=pubsub_topic,
        )

        await asyncio.sleep(3)

        # Verify subject name preserved
        assert len(subjects_received) == 1
        assert subjects_received[0]["name"] == "device-sensor-42"
        assert subjects_received[0]["payload"]["temperature"] == 23.5

        # Cleanup
        await subscriber_instance.stop()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

        del os.environ["SUBSCRIPTION_TEST"]

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_topic(
        self,
        publisher_container,
        pubsub_project,
        pubsub_topic,
        subscriber_client,
    ):
        """
        Test multiple subscribers receiving the same events (fan-out pattern).
        """
        # Setup publisher handlers
        pub_on, pub_when, pub_middleware, pub_emit = publisher_container.handlers()

        # Register no-op handler (required for middleware to run)
        @pub_on("broadcast.event")
        async def noop_handler(ctx: EventContext):
            """No-op handler - only external dispatch"""
            pass

        # Create two subscriber services
        container1 = KRulesContainer()
        container2 = KRulesContainer()

        subscriber1 = PubSubSubscriber(
            event_bus=container1.event_bus(),
            subject_factory=container1.subject,
        )

        subscriber2 = PubSubSubscriber(
            event_bus=container2.event_bus(),
            subject_factory=container2.subject,
        )

        # Create separate subscriptions to same topic
        sub_path_1 = subscriber_client.subscription_path(pubsub_project, "sub-service-1")
        sub_path_2 = subscriber_client.subscription_path(pubsub_project, "sub-service-2")

        # Create or purge subscriptions
        for sub_path in [sub_path_1, sub_path_2]:
            try:
                subscriber_client.create_subscription(
                    request={"name": sub_path, "topic": pubsub_topic}
                )
            except Exception:
                # Subscription exists, purge old messages
                try:
                    response = subscriber_client.pull(
                        request={"subscription": sub_path, "max_messages": 100},
                        timeout=2,
                    )
                    if response.received_messages:
                        ack_ids = [msg.ack_id for msg in response.received_messages]
                        subscriber_client.acknowledge(
                            request={"subscription": sub_path, "ack_ids": ack_ids}
                        )
                except Exception:
                    pass  # Ignore purge errors

        # Setup handlers
        on1, _, _, _ = container1.handlers()
        on2, _, _, _ = container2.handlers()

        events1 = []
        events2 = []

        @on1("broadcast.event")
        async def service1_handler(ctx: EventContext):
            events1.append(ctx.payload["message"])

        @on2("broadcast.event")
        async def service2_handler(ctx: EventContext):
            events2.append(ctx.payload["message"])

        # Start subscribers individually with isolated env vars
        # (subscriber scans ALL SUBSCRIPTION_* vars, so we need to set/unset individually)
        os.environ["SUBSCRIPTION_SERVICE1"] = sub_path_1
        await subscriber1.start()
        del os.environ["SUBSCRIPTION_SERVICE1"]
        task1 = None  # Already started, no task to track

        os.environ["SUBSCRIPTION_SERVICE2"] = sub_path_2
        await subscriber2.start()
        del os.environ["SUBSCRIPTION_SERVICE2"]
        task2 = None  # Already started, no task to track

        await asyncio.sleep(2)

        # Publisher emits one event
        subject = publisher_container.subject("broadcast")

        await pub_emit(
            "broadcast.event",
            subject,
            {"message": "Hello all services!"},
            topic=pubsub_topic,
        )

        await asyncio.sleep(3)

        # Both subscribers should receive the event
        assert len(events1) == 1
        assert len(events2) == 1
        assert events1[0] == "Hello all services!"
        assert events2[0] == "Hello all services!"

        # Cleanup
        await subscriber1.stop()
        await subscriber2.stop()

        # Purge and delete subscriptions
        for sub_path in [sub_path_1, sub_path_2]:
            try:
                # Purge remaining messages
                response = subscriber_client.pull(
                    request={"subscription": sub_path, "max_messages": 100},
                    timeout=2,
                )
                if response.received_messages:
                    ack_ids = [msg.ack_id for msg in response.received_messages]
                    subscriber_client.acknowledge(
                        request={"subscription": sub_path, "ack_ids": ack_ids}
                    )
            except Exception:
                pass

            try:
                subscriber_client.delete_subscription(request={"subscription": sub_path})
            except Exception:
                pass
