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
CloudEvents HTTP Dispatcher for KRules

Sends events to external HTTP endpoints using CloudEvents format (binary mode).
Integrates with KRules container for dependency injection.
"""

import logging
import uuid
import json
import inspect
from datetime import datetime, timezone
from typing import Callable, Optional, Union

import httpx
from cloudevents.pydantic import CloudEvent

from krules_core.subject import PayloadConst

logger = logging.getLogger(__name__)


class _JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder for functions and objects."""
    def default(self, obj):
        if inspect.isfunction(obj):
            return obj.__name__
        elif isinstance(obj, object):
            return str(type(obj))
        return json.JSONEncoder.default(self, obj)


class CloudEventsDispatcher:
    """
    Dispatcher that sends events to external HTTP endpoints using CloudEvents binary format.

    This dispatcher integrates with the KRules container and can be registered as middleware
    for transparent event dispatching via ctx.emit(..., dispatch_url="...").

    Features:
    - Modern CloudEvents v1.x with Pydantic models
    - Container-first dependency injection
    - Async HTTP via httpx
    - Preserves originid for event chain tracking
    - Supports extended properties and subject metadata
    - Dynamic dispatch URL (static string or callable)

    Args:
        dispatch_url: Target URL (string) or callable(subject, event_type) -> URL
        source: CloudEvent source identifier (e.g., "order-service")
        krules_container: KRulesContainer instance for subject factory
        default_dispatch_policy: Default policy ("direct" or "both") for middleware
        test: If True, returns extended info for testing (id, status, headers)

    Example:
        from krules_core.container import KRulesContainer
        from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware

        container = KRulesContainer()
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="order-service",
            krules_container=container,
        )

        # Option A: Register as middleware for transparent emit()
        middleware_func = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(middleware_func)

        on, when, middleware, emit = container.handlers()

        # Emit with dispatch_url triggers external dispatch
        await emit("order.created", subject, payload, dispatch_url="https://...")

        # Option B: Direct dispatch
        dispatcher.dispatch(
            event_type="order.created",
            subject=subject,
            payload={"amount": 100},
            dispatch_url="https://...",  # Override default
        )
    """

    def __init__(
        self,
        dispatch_url: Union[str, Callable],
        source: str,
        krules_container,
        default_dispatch_policy: str = "direct",
        test: bool = False,
    ):
        """
        Initialize CloudEventsDispatcher with container DI.

        Args:
            dispatch_url: Target URL or callable(subject, event_type) -> URL
            source: CloudEvent source identifier
            krules_container: KRulesContainer instance
            default_dispatch_policy: Default policy for middleware ("direct" or "both")
            test: Enable test mode (returns extended info)
        """
        if krules_container is None:
            raise ValueError(
                "krules_container is required. Pass KRulesContainer instance for DI."
            )

        self._dispatch_url = dispatch_url
        self._source = source
        self._krules = krules_container
        self.default_dispatch_policy = default_dispatch_policy
        self._test = test

        logger.info(
            f"CloudEventsDispatcher initialized with source='{source}', "
            f"dispatch_url={dispatch_url if isinstance(dispatch_url, str) else 'callable'}"
        )

    def dispatch(
        self,
        event_type: str,
        subject,
        payload: dict,
        **extra
    ) -> Union[str, tuple]:
        """
        Dispatch event to external HTTP endpoint using CloudEvents binary format.

        Args:
            event_type: CloudEvent type (e.g., "order.created")
            subject: Subject instance or string name
            payload: Event data (JSON-serializable dict)
            **extra: Additional metadata (dispatch_url, propertyname, etc.)

        Returns:
            Event ID (str) or tuple(id, status, headers) if test=True

        Raises:
            httpx.HTTPStatusError: If HTTP request fails

        Note:
            Extended properties from subject.get_ext_props() are included as
            CloudEvent extension attributes. PayloadConst.PROPERTY_NAME is
            automatically added if present in payload.
        """
        # Resolve subject (container DI)
        if isinstance(subject, str):
            subject = self._krules.subject(subject)

        # TODO: event_info should not be in Subject - it should be an event context
        # for tracking event chains. This architectural issue needs review.
        # For now, we preserve existing logic for backward compatibility.
        _event_info = subject.event_info()

        # Generate event ID
        _id = str(uuid.uuid4())
        logger.debug(f"Creating CloudEvent with id={_id}, type={event_type}")

        # Build extended properties
        ext_props = subject.get_ext_props().copy()

        # Add property name if present in payload
        property_name = payload.get(PayloadConst.PROPERTY_NAME)
        if property_name is not None:
            ext_props["propertyname"] = property_name

        # Add originid for event chain tracking
        # Preserve originid from event_info if exists, otherwise use current event ID
        ext_props["originid"] = str(_event_info.get("originid", _id))

        # Merge extra kwargs into extensions
        # Filter out special kwargs that aren't CloudEvent extensions
        special_kwargs = {"dispatch_url", "dispatch_policy"}
        for key, value in extra.items():
            if key not in special_kwargs:
                ext_props[key] = value

        # Create CloudEvent (modern Pydantic API)
        event = CloudEvent(
            attributes={
                "id": _id,
                "type": event_type,
                "source": self._source,
                "subject": str(subject),
                "time": datetime.now(timezone.utc),
                **ext_props,  # Extension attributes
            },
            data=payload,
        )

        # Resolve dispatch URL (static or dynamic)
        dispatch_url = extra.get("dispatch_url", self._dispatch_url)
        if callable(dispatch_url):
            dispatch_url = dispatch_url(subject, event_type)

        # Convert to CloudEvents binary format
        headers = {}
        for key, value in event.get_attributes().items():
            # Convert to ce-* headers (binary mode)
            header_name = f"ce-{key}"
            if isinstance(value, datetime):
                headers[header_name] = value.isoformat()
            else:
                headers[header_name] = str(value)

        # Set content type for data
        headers["content-type"] = "application/json"

        # Serialize payload
        body = json.dumps(payload, cls=_JSONEncoder)

        logger.info(
            f"Dispatching CloudEvent '{event_type}' (id={_id}) to {dispatch_url}"
        )

        # Send HTTP request (sync for now, httpx supports both sync/async)
        try:
            response = httpx.post(
                dispatch_url,
                headers=headers,
                content=body,
                timeout=30.0,
            )
            response.raise_for_status()

            logger.debug(
                f"CloudEvent dispatched successfully: {event_type} -> {dispatch_url} "
                f"(status={response.status_code})"
            )

            # Test mode returns extended info
            if self._test:
                return _id, response.status_code, headers

            return _id

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to dispatch CloudEvent '{event_type}' to {dispatch_url}: "
                f"HTTP {e.response.status_code} - {e.response.text}",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.error(
                f"Failed to dispatch CloudEvent '{event_type}' to {dispatch_url}: {e}",
                exc_info=True
            )
            raise
