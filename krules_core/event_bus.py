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
Modern async event bus for KRules 2.0

Replaces the legacy RuleFactory and EventRouter with a simpler,
async-native implementation.
"""

import asyncio
import fnmatch
import logging
from typing import Callable, Any, Optional, List
from dataclasses import dataclass
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class EventContext:
    """
    Context passed to event handlers.

    Attributes:
        event_type: Type of the event (e.g., "user.login")
        subject: Subject instance
        payload: Event payload dictionary
        property_name: Property name (for property change events)
        old_value: Previous value (for property change events)
        new_value: New value (for property change events)
    """
    event_type: str
    subject: Any
    payload: dict
    property_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    def __post_init__(self):
        """Extract property change metadata from payload"""
        if "property_name" in self.payload:
            self.property_name = self.payload.get("property_name")
            self.old_value = self.payload.get("old_value")
            self.new_value = self.payload.get("value")

    async def emit(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        subject: Optional[Any] = None
    ):
        """
        Emit a new event.

        Args:
            event_type: Type of event to emit
            payload: Event payload (defaults to empty dict)
            subject: Subject for the event (defaults to current subject)
        """
        if payload is None:
            payload = {}
        if subject is None:
            subject = self.subject

        await get_event_bus().emit(event_type, subject, payload)


@dataclass
class Handler:
    """Event handler with optional filters"""
    name: str
    func: Callable
    event_patterns: List[str]
    filters: List[Callable] = None
    is_async: bool = False

    def __post_init__(self):
        if self.filters is None:
            self.filters = []
        self.is_async = asyncio.iscoroutinefunction(self.func)

    def matches(self, event_type: str) -> bool:
        """Check if event type matches any pattern"""
        for pattern in self.event_patterns:
            if fnmatch.fnmatch(event_type, pattern):
                return True
        return False

    async def check_filters(self, ctx: EventContext) -> bool:
        """Execute all filters, return True if all pass"""
        for filter_func in self.filters:
            try:
                if asyncio.iscoroutinefunction(filter_func):
                    result = await filter_func(ctx)
                else:
                    result = filter_func(ctx)

                if not result:
                    return False
            except Exception as e:
                logger.warning(f"Filter failed in {self.name}: {e}")
                return False
        return True

    async def execute(self, ctx: EventContext):
        """Execute the handler function"""
        if self.is_async:
            await self.func(ctx)
        else:
            self.func(ctx)


class EventBus:
    """
    Async event bus for KRules 2.0

    Manages event handlers and routes events to matching handlers.
    Replaces the legacy RuleFactory/EventRouter system.
    """

    def __init__(self):
        self._handlers: List[Handler] = []
        self._middleware: List[Callable] = []

    def register(
        self,
        func: Callable,
        event_patterns: List[str],
        filters: Optional[List[Callable]] = None
    ) -> Handler:
        """
        Register an event handler.

        Args:
            func: Handler function
            event_patterns: List of event patterns to match
            filters: Optional list of filter functions

        Returns:
            Handler instance
        """
        handler = Handler(
            name=func.__name__,
            func=func,
            event_patterns=event_patterns,
            filters=filters or []
        )
        self._handlers.append(handler)
        logger.debug(f"Registered handler {handler.name} for {event_patterns}")
        return handler

    def unregister(self, name: str) -> int:
        """
        Unregister handlers by name.

        Args:
            name: Handler name to remove

        Returns:
            Number of handlers removed
        """
        count = 0
        self._handlers = [h for h in self._handlers if h.name != name or (count := count + 1) == 0]
        return count

    def unregister_all(self):
        """Remove all registered handlers"""
        count = len(self._handlers)
        self._handlers.clear()
        return count

    def add_middleware(self, middleware: Callable):
        """
        Add middleware that runs for all events.

        Middleware signature: async def middleware(ctx: EventContext, next: Callable)

        Example:
            async def log_middleware(ctx, next):
                print(f"Before: {ctx.event_type}")
                await next()
                print(f"After: {ctx.event_type}")

            event_bus.add_middleware(log_middleware)
        """
        self._middleware.append(middleware)

    async def emit(self, event_type: str, subject: Any, payload: dict):
        """
        Emit an event and execute all matching handlers.

        Args:
            event_type: Type of event
            subject: Subject instance
            payload: Event payload

        Example:
            await event_bus.emit("user.login", user, {"ip": "1.2.3.4"})
        """
        ctx = EventContext(
            event_type=event_type,
            subject=subject,
            payload=payload
        )

        logger.debug(f"Emitting event {event_type} on subject {subject}")

        # Find matching handlers
        matching_handlers = [h for h in self._handlers if h.matches(event_type)]

        logger.debug(f"Found {len(matching_handlers)} matching handlers")

        # Execute each matching handler
        for handler in matching_handlers:
            try:
                # Check filters
                if not await handler.check_filters(ctx):
                    logger.debug(f"Handler {handler.name} filtered out")
                    continue

                # Execute middleware chain
                if self._middleware:
                    await self._execute_with_middleware(ctx, handler)
                else:
                    await handler.execute(ctx)

            except Exception as e:
                logger.error(f"Error in handler {handler.name}: {e}", exc_info=True)
                # Continue processing other handlers

    async def _execute_with_middleware(self, ctx: EventContext, handler: Handler):
        """Execute handler with middleware chain"""
        async def execute_handler():
            await handler.execute(ctx)

        # Build middleware chain
        next_func = execute_handler
        for middleware in reversed(self._middleware):
            current_next = next_func

            async def wrapped(mw=middleware, nxt=current_next):
                await mw(ctx, nxt)

            next_func = wrapped

        await next_func()


# Global event bus instance
_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get or create the global event bus instance"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def set_event_bus(bus: EventBus):
    """Set the global event bus instance (for testing/custom setup)"""
    global _global_event_bus
    _global_event_bus = bus


def reset_event_bus():
    """Reset the global event bus (for testing)"""
    global _global_event_bus
    _global_event_bus = EventBus()