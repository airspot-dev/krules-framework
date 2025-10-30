#!/usr/bin/env python3
"""
Simple PubSub test with persistent topic/subscription
Topic: krules-integration-test
Subscription: krules-integration-test-sub
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from krules_core.container import KRulesContainer
from krules_core import EventContext
from krules_cloudevents_pubsub import CloudEventsDispatcher, PubSubSubscriber
from google.cloud import pubsub_v1

PROJECT_ID = "airspot-hub"
TOPIC_ID = "krules-integration-test"
SUBSCRIPTION_ID = "krules-integration-test-sub"


def test_1_direct_publish():
    """Test 1: Direct publish to PubSub (no KRules)"""
    print("\n" + "="*60)
    print("TEST 1: Direct Publish (Google PubSub Client)")
    print("="*60)

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    message = b"Test message from direct publish"
    future = publisher.publish(topic_path, message, test_type="direct")

    try:
        message_id = future.result(timeout=10)
        print(f"✅ Published message ID: {message_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to publish: {e}")
        return False


def test_2_verify_message():
    """Test 2: Verify message is in subscription"""
    print("\n" + "="*60)
    print("TEST 2: Verify Message in Subscription")
    print("="*60)

    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

    try:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 10},
            timeout=10,
        )

        if len(response.received_messages) > 0:
            print(f"✅ Found {len(response.received_messages)} message(s)")

            # Ack messages
            ack_ids = [msg.ack_id for msg in response.received_messages]
            subscriber.acknowledge(request={"subscription": subscription_path, "ack_ids": ack_ids})
            print(f"✅ Acknowledged messages")
            return True
        else:
            print(f"❌ No messages found")
            return False

    except Exception as e:
        print(f"❌ Failed to pull: {e}")
        return False


def test_3_krules_publisher():
    """Test 3: Publish via KRules CloudEventsDispatcher"""
    print("\n" + "="*60)
    print("TEST 3: KRules CloudEventsDispatcher")
    print("="*60)

    container = KRulesContainer()
    dispatcher = CloudEventsDispatcher(
        project_id=PROJECT_ID,
        source="test-service",
        krules_container=container,
    )

    subject = container.subject("test-subject-123")
    subject.set("test_prop", "value")

    print(f"→ Dispatching event...")
    dispatcher.dispatch(
        event_type="test.event",
        subject=subject,
        payload={"data": "from krules dispatcher", "timestamp": time.time()},
        topic=TOPIC_ID,
    )

    print(f"→ Waiting for publish to complete...")
    time.sleep(3)

    # Verify
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

    try:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 10},
            timeout=10,
        )

        if len(response.received_messages) > 0:
            print(f"✅ Found {len(response.received_messages)} message(s)")

            # Inspect
            msg = response.received_messages[0].message
            print(f"   Attributes: {dict(msg.attributes)}")

            # Ack
            ack_ids = [msg.ack_id for msg in response.received_messages]
            subscriber.acknowledge(request={"subscription": subscription_path, "ack_ids": ack_ids})

            return True
        else:
            print(f"❌ No messages found")
            return False

    except Exception as e:
        print(f"❌ Failed to verify: {e}")
        return False


async def test_4_krules_subscriber():
    """Test 4: KRules PubSubSubscriber"""
    print("\n" + "="*60)
    print("TEST 4: KRules PubSubSubscriber")
    print("="*60)

    # First, publish a message
    print(f"→ Publishing test message...")
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

    future = publisher.publish(
        topic_path,
        b'{"data": "test for subscriber"}',
        type="subscriber.test",
        source="test",
        subject="test-sub-123",
    )
    message_id = future.result(timeout=10)
    print(f"✅ Published message ID: {message_id}")

    # Now start subscriber
    print(f"→ Starting subscriber...")
    container = KRulesContainer()
    subscriber = PubSubSubscriber(
        event_bus=container.event_bus(),
        subject_factory=container.subject,
    )

    on, _, _, _ = container.handlers()

    received = []

    @on("subscriber.test")
    async def handler(ctx: EventContext):
        print(f"   🎯 Handler triggered!")
        print(f"      Event: {ctx.event_type}")
        print(f"      Subject: {ctx.subject.name}")
        received.append(ctx.event_type)

    os.environ["SUBSCRIPTION_TEST"] = f"projects/{PROJECT_ID}/subscriptions/{SUBSCRIPTION_ID}"

    task = asyncio.create_task(subscriber.start())

    print(f"→ Waiting for processing (15 seconds)...")
    await asyncio.sleep(15)

    await subscriber.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    del os.environ["SUBSCRIPTION_TEST"]

    if len(received) > 0:
        print(f"✅ Subscriber received {len(received)} event(s)")
        return True
    else:
        print(f"❌ Subscriber received 0 events")
        return False


def main():
    print("="*60)
    print("KRules PubSub Integration Tests")
    print(f"Project: {PROJECT_ID}")
    print(f"Topic: {TOPIC_ID}")
    print(f"Subscription: {SUBSCRIPTION_ID}")
    print("="*60)

    results = []

    # Test 1: Direct publish
    results.append(("Direct Publish", test_1_direct_publish()))

    # Test 2: Verify message
    results.append(("Verify Message", test_2_verify_message()))

    # Test 3: KRules publisher
    results.append(("KRules Publisher", test_3_krules_publisher()))

    # Test 4: KRules subscriber
    results.append(("KRules Subscriber", asyncio.run(test_4_krules_subscriber())))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")

    all_passed = all(r[1] for r in results)
    print("="*60)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("="*60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
