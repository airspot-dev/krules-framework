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
CloudEvents Publisher for Google Cloud PubSub.

This module provides a publisher (dispatcher) that sends CloudEvents to Google Cloud PubSub topics.
Used in conjunction with the subscriber module to enable transparent event handling across services.
"""

import inspect
import json
import uuid
from datetime import datetime, timezone
from pprint import pprint

from cloudevents.pydantic import CloudEvent
from google.cloud import pubsub_v1

from krules_core.route.dispatcher import BaseDispatcher
from krules_core.subject import PayloadConst


class _JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if inspect.isfunction(obj):
            return obj.__name__
        elif isinstance(obj, object):
            return str(type(obj))
        return json.JSONEncoder.default(self, obj)


def _callback(publish_future, exception_handler=None):
    try:
        publish_future.result(timeout=60)
    except Exception as ex:
        if exception_handler is not None:
            exception_handler(ex)
        else:
            raise


class CloudEventsDispatcher(BaseDispatcher):
    """
    CloudEvents publisher/dispatcher for Google Cloud PubSub.

    Sends events to PubSub topics in CloudEvents format. Typically used via
    dispatcher middleware to enable transparent publishing of events with
    `topic` metadata.

    Container-first design: Requires krules_container to be injected for
    subject creation and dependency injection.
    """

    def __init__(self, project_id, source, krules_container, topic_id=None, batch_settings=(), publisher_options=(), publisher_kwargs={}, default_dispatch_policy="direct"):
        """
        Initialize CloudEvents publisher.

        Args:
            project_id: GCP project ID
            source: CloudEvent source identifier (e.g., "my-service.orders")
            krules_container: KRules IoC container (required for subject creation)
            topic_id: Default PubSub topic ID (optional, can be overridden per-event with 'topic' kwarg)
                     If None, 'topic' must be specified in each dispatch() call or via middleware metadata
            batch_settings: PubSub batch settings
            publisher_options: PubSub publisher options
            publisher_kwargs: Additional publisher kwargs
            default_dispatch_policy: Default dispatch policy when 'dispatch_policy' not specified
                                    (default: "direct" - only dispatch, skip local handlers)
                                    Options: "direct" | "both"

        Example:
            from krules_core.container import KRulesContainer
            from krules_cloudevents_pubsub.publisher import CloudEventsDispatcher

            container = KRulesContainer()

            dispatcher = CloudEventsDispatcher(
                project_id="my-project",
                source="my-service",
                krules_container=container,
                topic_id="events",  # Optional default topic
            )
        """
        self._project_id = project_id
        self._topic_id = topic_id
        self._source = source
        self._krules = krules_container
        self._default_dispatch_policy = default_dispatch_policy
        self._publisher = pubsub_v1.PublisherClient(
            batch_settings=batch_settings,
            publisher_options=publisher_options,
            **publisher_kwargs
        )

    @property
    def default_dispatch_policy(self):
        """Get the default dispatch policy"""
        return self._default_dispatch_policy

    async def dispatch(self, event_type, subject, payload, **extra):
        """
        Dispatch an event to Google Cloud PubSub (async).

        Converts the event to CloudEvents format and publishes to the specified topic.
        The topic can be specified via constructor, 'topic' kwarg, or middleware metadata.

        Args:
            event_type: Event type string (e.g., "order.confirmed")
            subject: Subject instance or subject name string
            payload: Event payload dictionary
            **extra: Additional CloudEvent attributes
                topic: PubSub topic ID (overrides default)
                dataschema: CloudEvent dataschema URI
                exception_handler: Callback for publish errors

        Example:
            # Via middleware (recommended)
            @on("order.created")
            async def handler(ctx):
                await ctx.emit("order.confirmed", ctx.subject, {...}, topic="orders")

            # Direct dispatch
            await dispatcher.dispatch("order.confirmed", subject, {...}, topic="orders")
        """
        #import logfire
        #with logfire.span("PubSub Dispatcher", event=event_type, subject=subject, payload=payload, extra=extra):
        if isinstance(subject, str):
            subject = self._krules.subject(subject)
        _event_info = subject.event_info()

        _topic_id = self._topic_id
        if "topic" in extra:
            _topic_id = extra.pop("topic")

        if callable(_topic_id):
            _topic_id = self._topic_id(subject, event_type)

        if not _topic_id:
            return

        if _topic_id.startswith("projects/"):
            topic_path = _topic_id
        else:
            topic_path = self._publisher.topic_path(self._project_id, _topic_id)

        _id = str(uuid.uuid4())
        ext_props = await subject.get_ext_props()
        property_name = payload.get(PayloadConst.PROPERTY_NAME, None)
        if property_name is not None:
            ext_props.update({"propertyname": property_name})
        ext_props['originid'] = str(_event_info.get("originid", _id))
        ext_props["ce-type"] = event_type
        dataschema = extra.pop("dataschema", None)
        exception_handler = extra.pop("exception_handler", None)
        ext_props.update(extra)

        event = CloudEvent(
            attributes=dict(
                id=_id,
                type=event_type,
                source=self._source,
                subject=str(subject),
                time=datetime.now(timezone.utc),
                datacontenttype="application/json",
                dataschema=dataschema,
            ),
            data=payload,
        )

        event_obj = event.model_dump(exclude_unset=True, exclude_none=True)
        event_obj["data"] = json.dumps(event_obj["data"], cls=_JSONEncoder).encode()
        event_obj["time"] = event_obj["time"].isoformat()

        future = self._publisher.publish(topic_path, **event_obj, **ext_props, contentType="text/json")
        future.add_done_callback(lambda _future: _callback(_future, exception_handler))
