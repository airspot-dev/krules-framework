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
Pytest fixtures for CloudEvents PubSub tests using real GCP PubSub.

Uses persistent topic/subscription on real GCP:
- Project: airspot-hub
- Topic: krules-integration-test
- Subscription: krules-integration-test-sub
"""

import pytest
from google.cloud import pubsub_v1


# Real GCP configuration
PROJECT_ID = "airspot-hub"
TOPIC_ID = "krules-integration-test"
SUBSCRIPTION_ID = "krules-integration-test-sub"


@pytest.fixture
def pubsub_project():
    """Return real GCP project ID."""
    return PROJECT_ID


@pytest.fixture
def pubsub_topic(pubsub_project):
    """
    Return persistent test PubSub topic path.

    Note: Topic must exist in GCP (krules-integration-test)

    Returns:
        str: Topic path (e.g., "projects/airspot-hub/topics/krules-integration-test")
    """
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(pubsub_project, TOPIC_ID)
    return topic_path


@pytest.fixture
def pubsub_subscription(pubsub_project, pubsub_topic):
    """
    Return persistent test PubSub subscription path.

    Note: Subscription must exist in GCP (krules-integration-test-sub)

    Before tests: Purges old messages to clean state
    After tests: Purges messages to clean state

    Returns:
        str: Subscription path (e.g., "projects/airspot-hub/subscriptions/krules-integration-test-sub")
    """
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(pubsub_project, SUBSCRIPTION_ID)

    # Pre-cleanup: purge old messages before test
    try:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 100},
            timeout=2,
        )
        if response.received_messages:
            ack_ids = [msg.ack_id for msg in response.received_messages]
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": ack_ids}
            )
    except Exception:
        pass  # Ignore pre-cleanup errors

    yield subscription_path

    # Post-cleanup: purge messages after test
    try:
        response = subscriber.pull(
            request={"subscription": subscription_path, "max_messages": 100},
            timeout=2,
        )
        if response.received_messages:
            ack_ids = [msg.ack_id for msg in response.received_messages]
            subscriber.acknowledge(
                request={"subscription": subscription_path, "ack_ids": ack_ids}
            )
    except Exception:
        pass  # Ignore post-cleanup errors


@pytest.fixture
def publisher_client():
    """Return configured PubSub publisher client."""
    return pubsub_v1.PublisherClient()


@pytest.fixture
def subscriber_client():
    """Return configured PubSub subscriber client."""
    return pubsub_v1.SubscriberClient()
