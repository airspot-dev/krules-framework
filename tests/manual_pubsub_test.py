#!/usr/bin/env python3
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
Manual test script for PubSub publisher/subscriber with real GCP.

This script:
1. Creates temporary topic and subscription on real GCP
2. Tests publisher (CloudEventsDispatcher)
3. Tests subscriber (PubSubSubscriber)
4. Verifies end-to-end flow
5. Cleans up resources

Usage:
    uv run python tests/manual_pubsub_test.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from krules_core.container import KRulesContainer
from krules_core import EventContext
from krules_cloudevents_pubsub import (
    CloudEventsDispatcher,
    PubSubSubscriber,
    create_dispatcher_middleware,
)
from google.cloud import pubsub_v1


# Configuration
PROJECT_ID = "airspot-hub"
TOPIC_ID = f"krules-test-topic-{int(time.time())}"
SUBSCRIPTION_ID = f"krules-test-sub-{int(time.time())}"


def setup_pubsub_resources():
    """Create temporary PubSub topic and subscription."""
    print(f"📡 Creating PubSub resources in project: {PROJECT_ID}")

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    # Create topic
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    try:
        publisher.create_topic(request={"name": topic_path})
        print(f"✅ Created topic: {TOPIC_ID}")
    except Exception as e:
        print(f"❌ Failed to create topic: {e}")
        raise

    # Create subscription
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)
    try:
        subscriber.create_subscription(
            request={"name": subscription_path, "topic": topic_path}
        )
        print(f"✅ Created subscription: {SUBSCRIPTION_ID}")
    except Exception as e:
        print(f"❌ Failed to create subscription: {e}")
        publisher.delete_topic(request={"topic": topic_path})
        raise

    return topic_path, subscription_path


def cleanup_pubsub_resources():
    """Delete temporary PubSub resources."""
    print(f"\n🧹 Cleaning up resources...")

    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()

    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

    try:
        subscriber.delete_subscription(request={"subscription": subscription_path})
        print(f"✅ Deleted subscription: {SUBSCRIPTION_ID}")
    except Exception as e:
        print(f"⚠️  Failed to delete subscription: {e}")

    try:
        publisher.delete_topic(request={"topic": topic_path})
        print(f"✅ Deleted topic: {TOPIC_ID}")
    except Exception as e:
        print(f"⚠️  Failed to delete topic: {e}")


async def test_publisher(topic_path):
    """Test CloudEventsDispatcher (Publisher)."""
    print(f"\n📤 Testing Publisher...")

    # Create container and dispatcher
    container = KRulesContainer()
    dispatcher = CloudEventsDispatcher(
        project_id=PROJECT_ID,
        source="krules-test-publisher",
        krules_container=container,
    )

    # Register middleware
    middleware_func = create_dispatcher_middleware(dispatcher)
    container.event_bus().add_middleware(middleware_func)

    # Get handlers
    on, when, middleware, emit = container.handlers()

    # Create subject
    subject = container.subject("test-order-123")
    subject.set("status", "pending")

    # Emit event with topic (should trigger dispatcher)
    print(f"   → Emitting event: order.created")
    await emit(
        "order.created",
        subject,
        {
            "amount": 150.50,
            "currency": "USD",
            "timestamp": datetime.now().isoformat(),
        },
        topic=topic_path,
    )

    print(f"✅ Published event successfully")

    # Give PubSub time to propagate
    await asyncio.sleep(2)


async def test_subscriber(subscription_path):
    """Test PubSubSubscriber."""
    print(f"\n📥 Testing Subscriber...")

    # Create container
    container = KRulesContainer()

    # Create subscriber
    subscriber = PubSubSubscriber(
        event_bus=container.event_bus(),
        subject_factory=container.subject,
    )

    # Get handlers
    on, when, middleware, emit = container.handlers()

    # Track received events
    received_events = []

    @on("order.created")
    async def handle_order(ctx: EventContext):
        print(f"   🎯 Handler triggered!")
        print(f"      Event: {ctx.event_type}")
        print(f"      Subject: {ctx.subject.name}")
        print(f"      Payload: {ctx.payload}")

        received_events.append({
            "event_type": ctx.event_type,
            "subject_name": ctx.subject.name,
            "amount": ctx.payload.get("amount"),
            "currency": ctx.payload.get("currency"),
        })

    # Set environment variable for subscription
    os.environ["SUBSCRIPTION_TEST"] = subscription_path

    # Start subscriber
    print(f"   → Starting subscriber...")
    subscriber_task = asyncio.create_task(subscriber.start())

    # Give subscriber time to connect
    print(f"   → Waiting for subscriber to connect...")
    await asyncio.sleep(3)

    # Wait for message processing
    print(f"   → Waiting for messages...")
    await asyncio.sleep(5)

    # Stop subscriber
    print(f"   → Stopping subscriber...")
    await subscriber.stop()
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass

    # Clean env var
    del os.environ["SUBSCRIPTION_TEST"]

    # Verify results
    if len(received_events) > 0:
        print(f"✅ Subscriber received {len(received_events)} event(s)")
        event = received_events[0]
        print(f"   Event details:")
        print(f"   - Type: {event['event_type']}")
        print(f"   - Subject: {event['subject_name']}")
        print(f"   - Amount: {event['amount']} {event['currency']}")
        return True
    else:
        print(f"❌ Subscriber received 0 events (expected 1)")
        return False


async def test_end_to_end(topic_path, subscription_path):
    """Test end-to-end flow: start subscriber, publish, receive."""
    print(f"\n🔄 Testing End-to-End Flow...")

    # Create containers
    pub_container = KRulesContainer()
    sub_container = KRulesContainer()

    # Setup publisher
    dispatcher = CloudEventsDispatcher(
        project_id=PROJECT_ID,
        source="krules-test-publisher",
        krules_container=pub_container,
    )
    middleware_func = create_dispatcher_middleware(dispatcher)
    pub_container.event_bus().add_middleware(middleware_func)
    pub_on, pub_when, pub_middleware, pub_emit = pub_container.handlers()

    # Setup subscriber
    subscriber = PubSubSubscriber(
        event_bus=sub_container.event_bus(),
        subject_factory=sub_container.subject,
    )
    sub_on, sub_when, sub_middleware, sub_emit = sub_container.handlers()

    # Track received events
    received_events = []

    @sub_on("order.created")
    async def handle_order(ctx: EventContext):
        print(f"   🎯 Handler triggered!")
        print(f"      Event: {ctx.event_type}")
        print(f"      Subject: {ctx.subject.name}")
        print(f"      Payload: {ctx.payload}")

        received_events.append({
            "event_type": ctx.event_type,
            "subject_name": ctx.subject.name,
            "amount": ctx.payload.get("amount"),
            "currency": ctx.payload.get("currency"),
        })

    # START SUBSCRIBER FIRST
    os.environ["SUBSCRIPTION_TEST"] = subscription_path
    print(f"   → Starting subscriber...")
    subscriber_task = asyncio.create_task(subscriber.start())

    # Wait for subscriber to be ready
    print(f"   → Waiting for subscriber to connect (10 seconds)...")
    await asyncio.sleep(10)

    # NOW PUBLISH
    print(f"   → Publishing event...")
    subject = pub_container.subject("test-order-456")
    subject.set("status", "pending")

    await pub_emit(
        "order.created",
        subject,
        {
            "amount": 250.75,
            "currency": "EUR",
            "timestamp": datetime.now().isoformat(),
        },
        topic=topic_path,
    )

    print(f"   ✅ Event emitted (via middleware)")

    # Wait for publish to complete (dispatcher uses fire-and-forget)
    print(f"   → Waiting for publish to complete...")
    await asyncio.sleep(5)

    # Verify message is in PubSub
    print(f"   → Checking messages in subscription...")
    subscriber_client = pubsub_v1.SubscriberClient()
    try:
        response = subscriber_client.pull(
            request={"subscription": subscription_path, "max_messages": 10},
            timeout=10,
        )
    except Exception as e:
        print(f"   ⚠️  Error pulling messages: {e}")
        response = type('obj', (object,), {'received_messages': []})()

    if len(response.received_messages) > 0:
        print(f"   ✅ Found {len(response.received_messages)} message(s) in PubSub")
        # Ack them so subscriber can process
        ack_ids = [msg.ack_id for msg in response.received_messages]
        subscriber_client.acknowledge(request={"subscription": subscription_path, "ack_ids": ack_ids})

        # Inspect first message
        msg = response.received_messages[0].message
        print(f"   📩 Message attributes: {dict(msg.attributes)}")
        print(f"   📩 Message data (first 100 chars): {msg.data[:100]}")
    else:
        print(f"   ⚠️  No messages found in PubSub subscription!")

    # Wait for processing
    print(f"   → Waiting for subscriber to process (10 seconds)...")
    await asyncio.sleep(10)

    # Stop subscriber
    print(f"   → Stopping subscriber...")
    await subscriber.stop()
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass

    del os.environ["SUBSCRIPTION_TEST"]

    # Verify
    if len(received_events) > 0:
        print(f"✅ End-to-end test PASSED - received {len(received_events)} event(s)")
        event = received_events[0]
        print(f"   Event details:")
        print(f"   - Type: {event['event_type']}")
        print(f"   - Subject: {event['subject_name']}")
        print(f"   - Amount: {event['amount']} {event['currency']}")
        return True
    else:
        print(f"❌ End-to-end test FAILED - received 0 events (expected 1)")
        return False


async def main():
    """Run complete end-to-end test."""
    print("=" * 60)
    print("KRules CloudEvents PubSub - Manual Integration Test")
    print("=" * 60)

    topic_path = None
    subscription_path = None
    success = False

    try:
        # Setup
        topic_path, subscription_path = setup_pubsub_resources()

        # Test end-to-end (subscriber first, then publisher)
        success = await test_end_to_end(topic_path, subscription_path)

    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if topic_path and subscription_path:
            cleanup_pubsub_resources()

    # Summary
    print("\n" + "=" * 60)
    if success:
        print("✅ TEST PASSED - Publisher and Subscriber working correctly!")
    else:
        print("❌ TEST FAILED - Check output above for details")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
