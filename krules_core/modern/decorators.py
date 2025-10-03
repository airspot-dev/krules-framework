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
Decorators for modern event handlers.

Provides @on and @when decorators that integrate seamlessly with
the existing rule system using RuleFactory under the hood.
"""

import asyncio
import inspect
import fnmatch
from typing import Callable, Union, List, Optional
from functools import wraps

from .context import EventContext


# Global registry for handlers (used during registration)
_handler_registry = []


class Handler:
    """
    Internal handler wrapper that integrates with existing rule system.

    Converts modern decorator-based handlers into legacy Rule format
    for full backward compatibility.
    """

    def __init__(self, func: Callable, event_patterns: List[str]):
        self.func = func
        self.event_patterns = event_patterns
        self.filters = []
        self.name = func.__name__
        self.is_async = asyncio.iscoroutinefunction(func)

    def add_filter(self, filter_func: Callable):
        """Add a filter condition"""
        self.filters.append(filter_func)

    async def _call_func(self, ctx: EventContext):
        """Call the handler function (async or sync)"""
        if self.is_async:
            return await self.func(ctx)
        else:
            return self.func(ctx)

    def matches_event(self, event_type: str) -> bool:
        """Check if this handler should process the event"""
        for pattern in self.event_patterns:
            if fnmatch.fnmatch(event_type, pattern):
                return True
        return False

    async def should_execute(self, ctx: EventContext) -> bool:
        """Check all filter conditions"""
        for filter_func in self.filters:
            try:
                if asyncio.iscoroutinefunction(filter_func):
                    result = await filter_func(ctx)
                else:
                    result = filter_func(ctx)

                if not result:
                    return False
            except Exception:
                # Filter failed = don't execute
                return False
        return True

    async def execute(self, event_type: str, subject, payload: dict):
        """Execute the handler if conditions match"""
        if not self.matches_event(event_type):
            return

        ctx = EventContext(
            event_type=event_type,
            subject=subject,
            payload=payload
        )

        if await self.should_execute(ctx):
            await self._call_func(ctx)

    def to_legacy_rule(self):
        """
        Convert this modern handler to a legacy Rule definition.

        This enables full backward compatibility by registering modern
        handlers as standard rules in the existing system.
        """
        from krules_core.base_functions.filters import FilterFunction
        from krules_core.base_functions.processing import ProcessingFunction

        handler = self

        # Create filter adapters
        class ModernFilterAdapter(FilterFunction):
            """Adapter to wrap modern filter functions as legacy FilterFunction"""

            def __init__(self, filter_func: Callable):
                super().__init__()
                self.filter_func = filter_func

            def execute(self) -> bool:
                """Called by rule engine with self bound to RuleFunctionBase"""
                ctx = EventContext(
                    event_type=self.event_type,
                    subject=self.subject,
                    payload=self.payload
                )

                if asyncio.iscoroutinefunction(self.filter_func):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Create task but wait synchronously
                            import nest_asyncio
                            nest_asyncio.apply()
                            return loop.run_until_complete(self.filter_func(ctx))
                        else:
                            return loop.run_until_complete(self.filter_func(ctx))
                    except RuntimeError:
                        # No event loop
                        return asyncio.run(self.filter_func(ctx))
                else:
                    return self.filter_func(ctx)

        # Create processing adapter
        class ModernProcessingAdapter(ProcessingFunction):
            """Adapter to wrap modern handler as legacy ProcessingFunction"""

            def execute(self):
                """Called by rule engine with self bound to RuleFunctionBase"""
                ctx = EventContext(
                    event_type=self.event_type,
                    subject=self.subject,
                    payload=self.payload
                )

                if handler.is_async:
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            import nest_asyncio
                            nest_asyncio.apply()
                            return loop.run_until_complete(handler._call_func(ctx))
                        else:
                            return loop.run_until_complete(handler._call_func(ctx))
                    except RuntimeError:
                        return asyncio.run(handler._call_func(ctx))
                else:
                    return handler._call_func(ctx)

        # Convert filters
        legacy_filters = [ModernFilterAdapter(f) for f in self.filters]

        # Return rule definition dict
        return {
            "name": self.name,
            "subscribe_to": self.event_patterns,
            "data": {
                "filters": legacy_filters,
                "processing": [ModernProcessingAdapter()]
            }
        }


def on(*event_patterns: str):
    """
    Decorator to register a function as an event handler.

    Supports glob patterns for matching multiple events.

    Args:
        *event_patterns: One or more event patterns (e.g., "user.login", "user.*")

    Example:
        @on("user.login")
        async def handle_login(ctx):
            user = ctx.subject
            user.set("last_login", datetime.now())

        @on("device.*")  # Matches device.created, device.updated, etc.
        async def handle_device_event(ctx):
            print(f"Device event: {ctx.event_type}")

        @on("order.created", "order.updated")  # Multiple patterns
        async def handle_order(ctx):
            pass
    """
    def decorator(func: Callable):
        handler = Handler(func, list(event_patterns))
        _handler_registry.append(handler)

        # Store handler reference on function for @when decorator
        func._krules_handler = handler

        return func

    return decorator


def when(*conditions: Callable[[EventContext], bool]):
    """
    Decorator to add filter conditions to a handler.

    Can be stacked multiple times (ALL conditions must pass).

    Args:
        *conditions: One or more filter functions that return bool

    Example:
        @on("user.login")
        @when(lambda ctx: ctx.subject.get("status") == "active")
        @when(lambda ctx: ctx.payload.get("ip") not in blocked_ips)
        async def handle_active_user_login(ctx):
            pass

        # Reusable filters
        def is_admin(ctx):
            return ctx.payload.get("role") == "admin"

        @on("admin.action")
        @when(is_admin)
        async def handle_admin_action(ctx):
            pass
    """
    def decorator(func: Callable):
        if hasattr(func, "_krules_handler"):
            handler = func._krules_handler
            for condition in conditions:
                handler.add_filter(condition)
        else:
            raise ValueError(
                "@when must be used after @on decorator. "
                "Use @on first, then @when."
            )
        return func

    return decorator


def route_event(
    event_type: str,
    subject,
    payload: Optional[dict] = None,
    dispatch_policy: Optional[str] = None
):
    """
    Manually route an event through the system.

    Useful for emitting events outside of handlers or in synchronous code.

    Args:
        event_type: Type of event to emit
        subject: Subject instance or name
        payload: Event payload (defaults to empty dict)
        dispatch_policy: Routing policy (uses default if None)

    Example:
        from krules_core.providers import subject_factory
        from krules_core.modern import route_event

        user = subject_factory("user-123")
        route_event("user.updated", user, {"field": "email"})
    """
    from krules_core.providers import event_router_factory
    from krules_core.route.router import DispatchPolicyConst

    if payload is None:
        payload = {}
    if dispatch_policy is None:
        dispatch_policy = DispatchPolicyConst.DEFAULT

    event_router_factory().route(
        event_type,
        subject,
        payload,
        dispatch_policy=dispatch_policy
    )


def register_modern_handlers():
    """
    Register all modern handlers with the existing rule system.

    This registers handlers directly with the EventRouter as callables,
    bypassing the complex Rule/_Rule system for simplicity.

    Example:
        # At the end of your handlers file
        from krules_core.modern import register_modern_handlers

        @on("user.login")
        async def handle_login(ctx):
            pass

        # Register all defined handlers
        register_modern_handlers()
    """
    from krules_core.providers import event_router_factory

    router = event_router_factory()

    for handler in _handler_registry:
        # Create a wrapper callable that matches _Rule._process signature
        def create_wrapper(h: Handler):
            def wrapper(event_type: str, subject, payload: dict):
                """Wrapper that matches the signature expected by EventRouter"""
                ctx = EventContext(
                    event_type=event_type,
                    subject=subject,
                    payload=payload
                )

                # Check filters synchronously
                for filter_func in h.filters:
                    try:
                        if asyncio.iscoroutinefunction(filter_func):
                            # Run async filter synchronously
                            try:
                                loop = asyncio.get_event_loop()
                            except RuntimeError:
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)

                            result = loop.run_until_complete(filter_func(ctx))
                        else:
                            result = filter_func(ctx)

                        if not result:
                            return  # Filter failed, stop execution
                    except Exception:
                        return  # Filter error, stop execution

                # Execute handler
                if h.is_async:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    loop.run_until_complete(h._call_func(ctx))
                else:
                    h._call_func(ctx)

            return wrapper

        # Register wrapper for each event pattern
        for pattern in handler.event_patterns:
            # Create a mock _Rule object with just the _process method
            class MockRule:
                def __init__(self, process_func):
                    self._process = process_func
                    self.name = handler.name

            mock_rule = MockRule(create_wrapper(handler))
            router.register(mock_rule, pattern)

    # Clear registry after registration
    _handler_registry.clear()


# Auto-register on module import (optional, can be disabled)
def _auto_register_on_exit():
    """Auto-register handlers when Python exits"""
    if _handler_registry:
        register_modern_handlers()


import atexit
atexit.register(_auto_register_on_exit)