import os
import socket
import pytest
from google.cloud import pubsub_v1
from google.api_core import exceptions
from typing import AsyncGenerator


def is_emulator_running(host: str = "localhost", port: int = 8085) -> bool:
    """Check if the pubsub emulator is running."""
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except (socket.timeout, ConnectionRefusedError):
        return False


@pytest.fixture(scope="session", autouse=True)
def pubsub_emulator():
    """Configure pubsub emulator and verify it's running."""
    os.environ["PUBSUB_EMULATOR_HOST"] = "localhost:8085"

    if not is_emulator_running():
        pytest.exit("""
PubSub emulator not running! 
Please start it using the following command in a separate terminal:

    gcloud beta emulators pubsub start --host-port=localhost:8085

Then run the tests again.
""")
    yield


@pytest.fixture(scope="function")
def clean_pubsub_emulator():
    """Clean up any existing topics and subscriptions before each test."""
    publisher = pubsub_v1.PublisherClient()
    subscriber = pubsub_v1.SubscriberClient()
    project_path = f"projects/test-project"

    try:
        # Clean up existing subscriptions
        for subscription in subscriber.list_subscriptions(request={"project": project_path}):
            try:
                subscriber.delete_subscription(request={"subscription": subscription.name})
            except Exception:
                pass

        # Clean up existing topics
        for topic in publisher.list_topics(request={"project": project_path}):
            try:
                publisher.delete_topic(request={"topic": topic.name})
            except Exception:
                pass
    except Exception as e:
        print(f"Warning: Cleanup failed: {e}")

    yield


@pytest.fixture
def pubsub_project() -> str:
    """Provide a project ID for testing."""
    return "test-project"


@pytest.fixture
def pubsub_topic(clean_pubsub_emulator, pubsub_project: str) -> str:
    """Create a test topic and return its path."""
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(pubsub_project, "test-topic")

    try:
        publisher.create_topic(request={"name": topic_path})
    except exceptions.AlreadyExists:
        # First try to delete it
        try:
            publisher.delete_topic(request={"topic": topic_path})
            publisher.create_topic(request={"name": topic_path})
        except Exception as e:
            pytest.fail(f"Failed to recreate topic: {e}")
    except Exception as e:
        pytest.fail(f"Failed to create topic: {e}")

    try:
        yield topic_path
    finally:
        try:
            publisher.delete_topic(request={"topic": topic_path})
        except Exception:
            pass


@pytest.fixture
def pubsub_subscription(clean_pubsub_emulator, pubsub_project: str, pubsub_topic: str) -> str:
    """Create a test subscription and return its path."""
    subscriber = pubsub_v1.SubscriberClient()
    subscription_path = subscriber.subscription_path(pubsub_project, "test-sub")

    try:
        subscriber.create_subscription(
            request={
                "name": subscription_path,
                "topic": pubsub_topic
            }
        )
    except exceptions.AlreadyExists:
        # First try to delete it
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
            subscriber.create_subscription(
                request={
                    "name": subscription_path,
                    "topic": pubsub_topic
                }
            )
        except Exception as e:
            pytest.fail(f"Failed to recreate subscription: {e}")
    except Exception as e:
        pytest.fail(f"Failed to create subscription: {e}")

    try:
        yield subscription_path
    finally:
        try:
            subscriber.delete_subscription(request={"subscription": subscription_path})
        except Exception:
            pass