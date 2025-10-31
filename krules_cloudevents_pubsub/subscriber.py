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
Google Cloud PubSub Subscriber with KRules EventBus integration.

This module provides a container-first subscriber that bridges Google Cloud PubSub
to the KRules EventBus, enabling transparent event handling across services.

Events received from PubSub topics are automatically emitted on the local EventBus,
triggering registered @on handlers without any code changes.
"""

import asyncio
import os
import json
import logging
from typing import Optional
from contextlib import asynccontextmanager
from datetime import datetime

from google.cloud import pubsub_v1
from cloudevents.http import CloudEvent


class PubSubSubscriber:
    """
    PubSub subscriber that bridges Google Cloud PubSub to KRules EventBus.

    Receives CloudEvents from PubSub topics and emits them on the local EventBus,
    triggering registered @on handlers transparently.

    Container-first design: Requires event_bus and subject_factory to be injected
    from KRulesContainer.

    Example:
        # In application container
        from krules_core.container import KRulesContainer
        from krules_cloudevents_pubsub.subscriber import PubSubSubscriber

        container = KRulesContainer()

        subscriber = PubSubSubscriber(
            event_bus=container.event_bus(),
            subject_factory=container.subject,
        )

        # Register handlers using standard @on syntax
        on, when, middleware, emit = container.handlers()

        @on("order.confirmed")
        async def process_order(ctx):
            # Triggered when PubSub receives order.confirmed event
            logger.info(f"Processing order for {ctx.subject.name}")

        # Start subscriber
        await subscriber.start()
    """

    def __init__(self, event_bus, subject_factory, logger: Optional[logging.Logger] = None):
        """
        Initialize PubSubSubscriber with injected dependencies.

        Args:
            event_bus: EventBus instance from KRulesContainer (required)
            subject_factory: Subject factory callable from KRulesContainer (required)
            logger: Optional logger instance. If not provided, creates a default logger.

        Raises:
            ValueError: If event_bus or subject_factory is None
        """
        if event_bus is None:
            raise ValueError(
                "event_bus is required. Use KRulesContainer to inject dependencies. "
                "Example: PubSubSubscriber(event_bus=container.event_bus(), ...)"
            )

        if subject_factory is None:
            raise ValueError(
                "subject_factory is required. Use KRulesContainer to inject dependencies. "
                "Example: PubSubSubscriber(subject_factory=container.subject, ...)"
            )

        self.event_bus = event_bus
        self.subject_factory = subject_factory
        self.logger = logger or logging.getLogger(__name__)

        self.message_queue = asyncio.Queue()
        self.loop = None  # Will be set in start() when we have a running loop
        self.subscription_tasks = []
        self._running = False

    def _message_callback(self, message):
        """Callback for PubSub messages - adds them to the async queue."""
        asyncio.run_coroutine_threadsafe(self.message_queue.put(message), self.loop)

    def _create_cloud_event(self, message: pubsub_v1.subscriber.message.Message) -> CloudEvent:
        """
        Create a CloudEvent from a PubSub message.

        Converts PubSub message to CloudEvents format, preserving all attributes
        and handling both JSON and binary data.

        Args:
            message: PubSub message

        Returns:
            CloudEvent instance
        """
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
        """
        Process a PubSub message by emitting it on the local EventBus.

        This method:
        1. Converts PubSub message to CloudEvent
        2. Extracts event type, subject, and payload
        3. Creates Subject instance using injected factory
        4. Emits event on local EventBus (triggers @on handlers)
        5. Acknowledges message on success, nacks on error

        Args:
            message: PubSub message
        """
        try:
            # Convert to CloudEvent
            cloud_event = self._create_cloud_event(message)

            # Extract event components
            event_info = cloud_event.get_attributes()
            event_data = cloud_event.get_data()
            subject_name = event_info.get("subject")
            event_type = event_info.get("type")

            self.logger.debug(f"Processing event: {event_type} for subject: {subject_name}")

            # Create subject with injected factory
            subject = self.subject_factory(
                subject_name,
                event_info=event_info,
                event_data=event_data
            )

            # Store event_info in payload for backward compatibility
            if isinstance(event_data, dict):
                event_data["_event_info"] = dict(event_info)

            # Emit on local EventBus - triggers @on handlers transparently
            await self.event_bus.emit(event_type, subject, event_data)

            # Acknowledge successful processing
            message.ack()
            self.logger.debug(f"Successfully processed event: {event_type}")

        except Exception as e:
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            message.nack()

    async def _run_subscriber(self, subscription_path: str):
        """
        Run a subscriber for a specific subscription path.

        Creates a PubSub client and subscribes to the specified path,
        routing all messages to the processing queue.

        Args:
            subscription_path: Full GCP subscription path
                Format: projects/{project}/subscriptions/{subscription}
        """
        subscriber = pubsub_v1.SubscriberClient()
        future = subscriber.subscribe(subscription_path, callback=self._message_callback)
        self.logger.info(f"Listening for messages on {subscription_path}")

        try:
            # Use asyncio.to_thread instead of loop.run_in_executor (Python 3.9+)
            await asyncio.to_thread(future.result)
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
        """
        Start processing subscriptions from environment variables.

        Scans environment for variables starting with "SUBSCRIPTION_" and
        starts a subscriber for each one.

        Environment variables format:
            SUBSCRIPTION_<NAME>=projects/<project>/subscriptions/<subscription>

        Example:
            SUBSCRIPTION_ORDERS=projects/my-project/subscriptions/orders-sub
            SUBSCRIPTION_EVENTS=projects/my-project/subscriptions/events-sub
        """
        self._running = True

        # Capture the running event loop (safe to call in async context)
        self.loop = asyncio.get_running_loop()

        for env_var, value in os.environ.items():
            if env_var.startswith("SUBSCRIPTION_"):
                self.logger.info(f"Starting subscription: {value}")
                task = asyncio.create_task(self._run_subscriber(value))
                self.subscription_tasks.append(task)

        if not self.subscription_tasks:
            self.logger.warning(
                "No SUBSCRIPTION_* environment variables found. "
                "No subscriptions will be active."
            )

        self.queue_task = asyncio.create_task(self._process_queue())

    async def stop(self):
        """
        Stop all subscriptions and clean up resources.

        Cancels all running subscription tasks.
        """
        self.logger.info("Stopping PubSubSubscriber...")
        self._running = False

        for task in self.subscription_tasks:
            task.cancel()
        self.queue_task.cancel()

        await asyncio.gather(*self.subscription_tasks, self.queue_task, return_exceptions=True)

        self.logger.info("PubSubSubscriber stopped")

    @classmethod
    async def create(cls, event_bus, subject_factory, logger: Optional[logging.Logger] = None) -> 'PubSubSubscriber':
        """
        Create and start a new PubSubSubscriber instance.

        Convenience method that creates and starts the subscriber in one call.

        Args:
            event_bus: EventBus instance from KRulesContainer
            subject_factory: Subject factory callable from KRulesContainer
            logger: Optional logger instance

        Returns:
            Started PubSubSubscriber instance

        Example:
            subscriber = await PubSubSubscriber.create(
                event_bus=container.event_bus(),
                subject_factory=container.subject,
            )
        """
        subscriber = cls(event_bus, subject_factory, logger)
        await subscriber.start()
        return subscriber


@asynccontextmanager
async def create_subscriber(event_bus, subject_factory, logger: Optional[logging.Logger] = None) -> PubSubSubscriber:
    """
    Create and manage a PubSubSubscriber instance as a context manager.

    Automatically starts the subscriber on entry and stops it on exit,
    ensuring proper cleanup even if exceptions occur.

    Args:
        event_bus: EventBus instance from KRulesContainer
        subject_factory: Subject factory callable from KRulesContainer
        logger: Optional logger instance

    Yields:
        Started PubSubSubscriber instance

    Example:
        from krules_core.container import KRulesContainer
        from krules_cloudevents_pubsub.subscriber import create_subscriber

        container = KRulesContainer()
        on, when, middleware, emit = container.handlers()

        # Register handlers
        @on("order.confirmed")
        async def process_order(ctx):
            logger.info(f"Processing: {ctx.subject.name}")

        # Use context manager for lifecycle
        async with create_subscriber(
            event_bus=container.event_bus(),
            subject_factory=container.subject,
        ) as subscriber:
            # Subscriber is running, handlers will be triggered
            await asyncio.sleep(3600)  # Keep alive
    """
    subscriber = await PubSubSubscriber.create(event_bus, subject_factory, logger)
    try:
        yield subscriber
    finally:
        await subscriber.stop()
