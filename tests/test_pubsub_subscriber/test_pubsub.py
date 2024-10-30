# tests/test_pubsub_subscriber/test_pubsub.py
import asyncio
import json
import logging
import os
from datetime import datetime
import pytest
from google.cloud import pubsub_v1
from cloudevents.http import CloudEvent

from krules_pubsub.subscriber import create_subscriber


@pytest.mark.asyncio
async def test_subscriber_basic_flow(pubsub_topic: str, pubsub_subscription: str):
    """Test basic message flow through the subscriber."""
    received_events = []

    async def handle_message(event: CloudEvent, **kwargs):
        received_events.append(event)

    os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription

    async with create_subscriber() as subscriber:
        subscriber.add_process_function_for_subject(
            "test-subject-.*",
            handle_message
        )

        await asyncio.sleep(1)

        publisher = pubsub_v1.PublisherClient()
        message_data = {"test": "message"}
        attributes = {"subject": "test-subject-1"}

        publisher.publish(
            pubsub_topic,
            json.dumps(message_data).encode(),
            **attributes
        ).result()

        await asyncio.sleep(2)

    assert len(received_events) == 1
    event = received_events[0]
    assert event.data == message_data
    assert event["subject"] == attributes["subject"]
    assert event["datacontenttype"] == "application/json"


@pytest.mark.asyncio
async def test_non_json_data(pubsub_topic: str, pubsub_subscription: str):
    """Test handling of non-JSON message data."""
    received_events = []

    async def handle_message(event: CloudEvent, **kwargs):
        received_events.append(event)

    os.environ["SUBSCRIPTION_TEST"] = pubsub_subscription

    async with create_subscriber() as subscriber:
        subscriber.add_process_function_for_subject(
            "test-subject-.*",
            handle_message
        )

        await asyncio.sleep(1)

        publisher = pubsub_v1.PublisherClient()
        message_data = b"binary data"
        attributes = {"subject": "test-subject-1"}

        publisher.publish(
            pubsub_topic,
            message_data,
            **attributes
        ).result()

        await asyncio.sleep(2)

    assert len(received_events) == 1
    event = received_events[0]
    assert event.data == message_data
    assert event["subject"] == attributes["subject"]
    assert event["datacontenttype"] == "application/octet-stream"