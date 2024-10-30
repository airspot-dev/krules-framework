# krules_pubsub/subscriber.py
import asyncio
import re
import os
import json
import logging
from typing import Callable, Dict, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime

from google.cloud import pubsub_v1
from cloudevents.http import CloudEvent

from krules_core.providers import subject_factory, event_router_factory
from krules_core.route.router import DispatchPolicyConst

class PubSubSubscriber:

    class KRulesEventRouterHandler:

        def __init__(self, logger: logging.Logger = None):
            if logger is None:
                logger = logging.getLogger(__name__)
            self.logger = logger

        async def __call__(self, message: CloudEvent, **kwargs):
            self.logger.debug(f"Received message with kwargs {kwargs}")
            event_info = message.get_attributes()
            event_data = message.get_data()
            subject = event_info.get("subject")
            event_type = event_info.get("type")

            subject = subject_factory(name=subject, event_info=event_info, event_data=event_data)

            event_data["_event_info"] = dict(event_info)  # TODO: KRUL-155

            event_router_factory().route(
                event_type, subject, event_data,
                dispatch_policy=DispatchPolicyConst.NEVER
            )

            self.logger.debug(message)

    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize a new PubSubSubscriber.

        Args:
            logger: Optional logger instance. If not provided, creates a default logger.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.message_queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor()
        self.loop = asyncio.get_event_loop()
        self.subscription_tasks = []
        self.process_functions: Dict[str, Tuple[re.Pattern, Callable]] = {}
        self._running = False

    def add_process_function_for_subject(self, subject_pattern: str, func: Callable):
        """
        Add a function to process messages matching a subject pattern.

        Args:
            subject_pattern: Regex pattern to match message subjects
            func: Async callback function(cloudevent, **pattern_matches)
        """
        compiled_pattern = re.compile(subject_pattern)
        self.process_functions[subject_pattern] = (compiled_pattern, func)
        self.logger.debug(f"Added process function for pattern: {subject_pattern}")

    def _message_callback(self, message):
        """Callback for PubSub messages - adds them to the async queue."""
        asyncio.run_coroutine_threadsafe(self.message_queue.put(message), self.loop)

    def _create_cloud_event(self, message: pubsub_v1.subscriber.message.Message) -> CloudEvent:
        """Create a CloudEvent from a PubSub message."""
        try:
            data = json.loads(message.data.decode())
            data_content_type = "application/json"
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = message.data
            data_content_type = "application/octet-stream"

        attributes = {
            "id": message.message_id,
            "source": message.attributes.get('source', f"//pubsub.googleapis.com/{message.message_id}"),
            "type": message.attributes.get('type', 'google.cloud.pubsub.message.v1'),
            "time": datetime.fromtimestamp(message.publish_time.timestamp()).isoformat(),
            "subject": message.attributes.get('subject', ''),
            "datacontenttype": data_content_type
        }

        # Add any additional attributes from the message
        for key, value in message.attributes.items():
            if key not in attributes:
                attributes[key] = value

        return CloudEvent(attributes, data)

    async def _process_message(self, message):
        """Process a single message by finding and calling matching handler."""
        try:
            subject = message.attributes.get('subject', '')
            processed = False

            # Convert message to CloudEvent
            cloud_event = self._create_cloud_event(message)

            for pattern, func in self.process_functions.values():
                match = pattern.match(subject)
                if match:
                    await func(cloud_event, **match.groupdict())
                    processed = True
                    break
            message.ack()
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            message.nack()

    async def _run_subscriber(self, subscription_path: str):
        """Run a subscriber for a specific subscription path."""
        subscriber = pubsub_v1.SubscriberClient()
        future = subscriber.subscribe(subscription_path, callback=self._message_callback)
        self.logger.info(f"Listening for messages on {subscription_path}")

        try:
            await self.loop.run_in_executor(self.executor, future.result)
        except Exception as ex:
            self.logger.error(f"Error in subscription {subscription_path}: {ex}")
        finally:
            if self._running:  # Only log if not in shutdown
                self.logger.warning(f"Subscription {subscription_path} ended unexpectedly")
            future.cancel()
            subscriber.close()

    async def _process_queue(self):
        """Process messages from the queue continuously."""
        while self._running:
            try:
                message = await self.message_queue.get()
                await self._process_message(message)
                self.message_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing queue: {e}")

    async def start(self):
        """Start processing subscriptions from environment variables."""
        self._running = True
        for env_var, value in os.environ.items():
            if env_var.startswith("SUBSCRIPTION_"):
                self.logger.info(f"Starting subscription: {value}")
                task = asyncio.create_task(self._run_subscriber(value))
                self.subscription_tasks.append(task)

        self.queue_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        """Stop all subscriptions and clean up resources."""
        self._running = False
        for task in self.subscription_tasks:
            task.cancel()
        self.queue_task.cancel()

        await asyncio.gather(*self.subscription_tasks, self.queue_task, return_exceptions=True)
        self.executor.shutdown(wait=True)

    @classmethod
    async def create(cls, logger: Optional[logging.Logger] = None) -> 'PubSubSubscriber':
        """
        Create and start a new PubSubSubscriber instance.

        Args:
            logger: Optional logger instance. If not provided, creates a default logger.
        """
        subscriber = cls(logger)
        await subscriber.start()
        return subscriber


# Move create_subscriber to the same module to avoid circular imports
@asynccontextmanager
async def create_subscriber(logger: Optional[logging.Logger] = None) -> PubSubSubscriber:
    """
    Create and manage a PubSubSubscriber instance.

    Args:
        logger: Optional logger instance. If not provided, creates a default logger.

    Usage:
        async with create_subscriber(logger=my_logger) as subscriber:
            subscriber.add_process_function_for_subject("pattern", handler)
            # ... do other stuff ...
    """
    subscriber = await PubSubSubscriber.create(logger)
    try:
        yield subscriber
    finally:
        await subscriber.stop()