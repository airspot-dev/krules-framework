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
Pytest fixtures for CloudEvents PubSub tests using Google Cloud PubSub Emulator.

The emulator provides a local PubSub service for testing without requiring
real GCP credentials or incurring costs.
"""

import os
import subprocess
import time
import socket
import pytest
from google.cloud import pubsub_v1
from google.api_core.exceptions import AlreadyExists


def find_free_port():
    """Find a free port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def pubsub_emulator():
    """
    Start Google Cloud PubSub emulator for the test session.

    Yields:
        str: Emulator host (e.g., "localhost:8085")
    """
    # Find free port
    port = find_free_port()
    emulator_host = f"localhost:{port}"

    # Set environment variable for all clients
    os.environ["PUBSUB_EMULATOR_HOST"] = emulator_host

    # Start emulator
    process = subprocess.Popen(
        ["gcloud", "beta", "emulators", "pubsub", "start", f"--host-port={emulator_host}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for emulator to be ready (check for successful connection)
    max_retries = 30
    for i in range(max_retries):
        try:
            # Try to create a test client
            publisher = pubsub_v1.PublisherClient()
            # Try to list topics (will fail if emulator not ready)
            list(publisher.list_topics(request={"project": f"projects/test-project"}))
            break
        except Exception:
            if i == max_retries - 1:
                process.kill()
                raise RuntimeError("PubSub emulator failed to start")
            time.sleep(0.5)

    yield emulator_host

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    # Clean up environment variable
    if "PUBSUB_EMULATOR_HOST" in os.environ:
        del os.environ["PUBSUB_EMULATOR_HOST"]


@pytest.fixture
def pubsub_project():
    """Return test project ID."""
    return "test-project"


@pytest.fixture
def pubsub_topic(pubsub_emulator, pubsub_project):
    """
    Create a test PubSub topic.

    Yields:
        str: Topic path (e.g., "projects/test-project/topics/test-topic")
    """
    topic_id = "test-topic"
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(pubsub_project, topic_id)

    try:
        publisher.create_topic(request={"name": topic_path})
    except AlreadyExists:
        pass

    yield topic_path

    # Cleanup
    try:
        publisher.delete_topic(request={"topic": topic_path})
    except Exception:
        pass


@pytest.fixture
def pubsub_subscription(pubsub_emulator, pubsub_project, pubsub_topic):
    """
    Create a test PubSub subscription.

    Yields:
        str: Subscription path (e.g., "projects/test-project/subscriptions/test-subscription")
    """
    subscription_id = "test-subscription"
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(pubsub_project, subscription_id)

    try:
        subscriber.create_subscription(
            request={"name": subscription_path, "topic": pubsub_topic}
        )
    except AlreadyExists:
        pass

    yield subscription_path

    # Cleanup
    try:
        subscriber.delete_subscription(request={"subscription": subscription_path})
    except Exception:
        pass


@pytest.fixture
def publisher_client(pubsub_emulator):
    """Return configured PubSub publisher client."""
    return pubsub_v1.PublisherClient()


@pytest.fixture
def subscriber_client(pubsub_emulator):
    """Return configured PubSub subscriber client."""
    return pubsub_v1.SubscriberClient()
