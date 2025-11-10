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
Factory for creating event handlers bound to a specific EventBus.

KRules 2.0 uses dependency injection via KRulesContainer.
All decorators and emit function are created from the container.

Example:
    from krules_core.container import KRulesContainer

    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()

    @on("user.login")
    @when(lambda ctx: ctx.subject.get("active"))
    async def handle_login(ctx):
        await emit("user.logged-in", ctx.subject)
"""

from typing import Callable, Any, Optional


def create_handlers(event_bus):
    """
    Factory for creating handler decorators bound to a specific event bus.

    This is called internally by KRulesContainer.handlers().
    Do not call this directly - use the container instead.

    Args:
        event_bus: EventBus instance to bind handlers to

    Returns:
        tuple: (on, when, middleware, emit) - decorators and emit function bound to the event bus

    Example:
        # Via container (recommended)
        from krules_core.container import KRulesContainer
        container = KRulesContainer()
        on, when, middleware, emit = container.handlers()

        # Direct (advanced use only)
        from krules_core.event_bus import EventBus
        from krules_core.handlers import create_handlers
        bus = EventBus()
        on, when, middleware, emit = create_handlers(bus)
    """

    def on(*event_patterns: str):
        """
        Decorator to register a function as an event handler.

        Supports glob patterns (*, ?) for matching multiple events.

        Args:
            *event_patterns: One or more event patterns

        Examples:
            # Single event
            @on("user.login")
            async def handle_login(ctx: EventContext):
                user = ctx.subject
                user.set("last_login", datetime.now())

            # Multiple events
            @on("user.created", "user.updated")
            async def handle_user_change(ctx: EventContext):
                await emit("user.changed", ctx.subject)

            # Glob patterns
            @on("device.*")  # Matches device.created, device.updated, etc.
            async def handle_device(ctx: EventContext):
                print(f"Device event: {ctx.event_type}")

            # Wildcard
            @on("*")  # Matches all events
            async def log_all(ctx: EventContext):
                logger.info(f"Event: {ctx.event_type}")
        """
        def decorator(func: Callable):
            # Check if @when was applied before @on (collect pending filters)
            pending_filters = getattr(func, "_krules_pending_filters", [])

            handler = event_bus.register(func, list(event_patterns), filters=pending_filters)

            # Store handler reference for @when decorator
            func._krules_handler = handler

            # Clear pending filters
            if hasattr(func, "_krules_pending_filters"):
                delattr(func, "_krules_pending_filters")

            return func

        return decorator


    def when(*conditions: Callable):
        """
        Add filter conditions to a handler.

        Multiple @when decorators can be stacked (ALL must pass).
        Can be used before or after @on decorator.

        Args:
            *conditions: One or more filter functions returning bool

        Examples:
            # Single filter
            @on("user.login")
            @when(lambda ctx: ctx.subject.get("status") == "active")
            async def handle_active_login(ctx: EventContext):
                pass

            # Multiple filters (all must pass)
            @on("admin.action")
            @when(lambda ctx: ctx.payload.get("role") == "admin")
            @when(lambda ctx: ctx.subject.get("verified") == True)
            async def handle_admin(ctx: EventContext):
                pass

            # Reusable filters
            def is_premium(ctx):
                return ctx.subject.get("tier") == "premium"

            def has_credit(ctx):
                return ctx.subject.get("credits", 0) > 0

            @on("feature.use")
            @when(is_premium)
            @when(has_credit)
            async def use_premium_feature(ctx: EventContext):
                ctx.subject.set("credits", lambda c: c - 1)

            # Property change filters
            @on("subject-property-changed")
            @when(lambda ctx: ctx.property_name == "temperature")
            @when(lambda ctx: ctx.new_value > 80)
            async def on_overheat(ctx: EventContext):
                await emit("alert.overheat", ctx.subject)
        """
        def decorator(func: Callable):
            if hasattr(func, "_krules_handler"):
                # Handler already registered - add filters directly
                handler = func._krules_handler
                handler.filters.extend(conditions)
            else:
                # Handler not yet registered - store pending filters
                # (happens when @when is applied before @on due to bottom-up execution)
                if not hasattr(func, "_krules_pending_filters"):
                    func._krules_pending_filters = []
                func._krules_pending_filters.extend(conditions)

            return func

        return decorator


    def middleware(func: Callable):
        """
        Register a middleware function that runs for all events.

        Middleware can inspect/modify context and control handler execution.

        Args:
            func: Middleware function with signature:
                  async def middleware(ctx: EventContext, next: Callable)

        Examples:
            # Logging middleware
            @middleware
            async def log_events(ctx: EventContext, next: Callable):
                logger.info(f"Event: {ctx.event_type} on {ctx.subject}")
                await next()  # Call next middleware/handler

            # Timing middleware
            @middleware
            async def track_timing(ctx: EventContext, next: Callable):
                start = time.time()
                await next()
                duration = time.time() - start
                metrics.timing(f"event.{ctx.event_type}", duration)

            # Authentication middleware
            @middleware
            async def require_auth(ctx: EventContext, next: Callable):
                if ctx.payload.get("authenticated"):
                    await next()
                else:
                    logger.warning("Unauthenticated event rejected")

            # Error handling middleware
            @middleware
            async def handle_errors(ctx: EventContext, next: Callable):
                try:
                    await next()
                except Exception as e:
                    logger.error(f"Handler failed: {e}")
                    await emit("error.handler_failed", ctx.subject, {"error": str(e)})
        """
        event_bus.add_middleware(func)
        return func


    async def emit(event_type: str, subject: Any, payload: Optional[dict] = None, **extra):
        """
        Emit an event directly (without context).

        Convenience function for emitting events outside handlers.

        Args:
            event_type: Type of event to emit
            subject: Subject instance
            payload: Event payload (defaults to empty dict)
            **extra: Extra kwargs (e.g., topic="alerts", dataschema="...")

        Example:
            from krules_core.container import KRulesContainer

            container = KRulesContainer()
            on, when, middleware, emit = container.handlers()

            user = container.subject("user-123")
            await emit("user.updated", user, {"field": "email"})

            # With extra kwargs for middleware
            await emit("alert.critical", device, {"temp": 95}, topic="alerts")
        """
        if payload is None:
            payload = {}

        await event_bus.emit(event_type, subject, payload, **extra)

    return on, when, middleware, emit
