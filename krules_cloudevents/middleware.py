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
Middleware for dispatching events to external HTTP endpoints via CloudEvents.

Integrates CloudEventsDispatcher with the modern EventBus middleware system.
"""

import logging
from typing import Callable
from .dispatch_policy import DispatchPolicyConst

logger = logging.getLogger(__name__)


def create_dispatcher_middleware(dispatcher):
    """
    Factory for creating dispatcher middleware with dependency injection.

    The middleware intercepts events with 'dispatch_url' metadata and dispatches them
    to external HTTP endpoints according to the dispatch policy.

    Dispatch Policy (kwarg: dispatch_policy):
        - DispatchPolicyConst.DIRECT (default): Dispatch to external URL ONLY, skip local handlers
        - DispatchPolicyConst.BOTH: Dispatch to external URL AND execute local handlers
        - DispatchPolicyConst.NEVER/DEFAULT/ALWAYS (deprecated): Legacy compatibility only

    Args:
        dispatcher: CloudEventsDispatcher instance (dependency injected)

    Returns:
        Middleware function ready to be registered on EventBus

    Example:
        from krules_cloudevents import CloudEventsDispatcher, create_dispatcher_middleware
        from krules_core.container import KRulesContainer
        from krules_cloudevents import DispatchPolicyConst

        # Create container
        container = KRulesContainer()

        # Create dispatcher
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="order-service",
            krules_container=container,
        )

        # Register middleware (factory pattern)
        dispatcher_mw = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(dispatcher_mw)

        # Get handlers (decorators and emit function)
        on, when, middleware, emit = container.handlers()

        # In handlers
        await ctx.emit("alert.critical", subject, payload, dispatch_url="https://...")  # DIRECT (default)
        await ctx.emit("order.created", subject, payload, dispatch_url="https://...", dispatch_policy=DispatchPolicyConst.BOTH)
    """
    async def dispatcher_middleware(ctx, next: Callable):
        """
        Middleware that dispatches events with 'dispatch_url' metadata to external endpoints.

        Behavior:
            1. If 'dispatch_url' not in metadata → only local handlers (skip dispatcher)
            2. If 'dispatch_url' in metadata:
                - Get dispatch_policy (default: dispatcher.default_dispatch_policy)
                - If DIRECT: dispatch externally, skip local handlers (no next())
                - If BOTH: dispatch externally + execute local handlers (next())
                - If legacy (NEVER/DEFAULT/ALWAYS): map to new policies with warning

        Guard: Dispatch only once per event (not per handler) using _dispatch_executed flag.

        Args:
            ctx: EventContext with metadata
            next: Next middleware/handler in chain
        """
        dispatch_url = ctx.get_metadata("dispatch_url")

        # No dispatch_url → only local handlers
        if dispatch_url is None:
            await next()
            return

        # Guard: dispatch only once per event (middleware runs per-handler)
        if ctx.get_metadata("_dispatch_executed"):
            # Already dispatched, just continue with handler
            await next()
            return

        # Mark as dispatched (run once per event)
        ctx.set_metadata("_dispatch_executed", True)

        # Get dispatch policy (default: dispatcher's default)
        dispatch_policy = ctx.get_metadata(
            "dispatch_policy",
            dispatcher.default_dispatch_policy
        )

        # Normalize legacy policies
        if dispatch_policy == DispatchPolicyConst.ALWAYS:
            logger.warning(
                f"dispatch_policy 'ALWAYS' is deprecated, use DispatchPolicyConst.BOTH instead. "
                f"Event: {ctx.event_type}"
            )
            dispatch_policy = DispatchPolicyConst.BOTH

        elif dispatch_policy == DispatchPolicyConst.DEFAULT:
            logger.warning(
                f"dispatch_policy 'DEFAULT' is deprecated, use DIRECT or BOTH explicitly. "
                f"Falling back to DIRECT. Event: {ctx.event_type}"
            )
            dispatch_policy = DispatchPolicyConst.DIRECT

        elif dispatch_policy == DispatchPolicyConst.NEVER:
            logger.warning(
                f"dispatch_policy 'NEVER' is deprecated. If you don't want external dispatch, "
                f"don't specify 'dispatch_url' kwarg. Skipping dispatch. Event: {ctx.event_type}"
            )
            # Skip dispatch, only local handlers
            await next()
            return

        # Validate policy
        if dispatch_policy not in (DispatchPolicyConst.DIRECT, DispatchPolicyConst.BOTH):
            logger.error(
                f"Invalid dispatch_policy '{dispatch_policy}' for event {ctx.event_type}. "
                f"Valid options: DispatchPolicyConst.DIRECT, DispatchPolicyConst.BOTH. "
                f"Falling back to DIRECT."
            )
            dispatch_policy = DispatchPolicyConst.DIRECT

        # Extract extra kwargs for dispatcher
        extra_kwargs = {"dispatch_url": dispatch_url}

        # Optional metadata passthrough
        for key in ("dataschema", "exception_handler"):
            value = ctx.get_metadata(key)
            if value is not None:
                extra_kwargs[key] = value

        # Dispatch to external URL
        try:
            logger.info(
                f"Dispatching event '{ctx.event_type}' to URL '{dispatch_url}' "
                f"(policy: {dispatch_policy})"
            )

            dispatcher.dispatch(
                event_type=ctx.event_type,
                subject=ctx.subject,
                payload=ctx.payload,
                **extra_kwargs
            )

            ctx.set_metadata("_dispatched", True)
            ctx.set_metadata("_dispatched_url", dispatch_url)

            logger.debug(f"Event '{ctx.event_type}' successfully dispatched to '{dispatch_url}'")

        except Exception as e:
            logger.error(
                f"Failed to dispatch event '{ctx.event_type}' to URL '{dispatch_url}': {e}",
                exc_info=True
            )
            ctx.set_metadata("_dispatch_error", str(e))
            # Don't raise - allow local handlers to continue even if dispatch fails

        # Execute local handlers based on policy
        if dispatch_policy == DispatchPolicyConst.BOTH:
            # BOTH: execute local handlers
            await next()
        elif dispatch_policy == DispatchPolicyConst.DIRECT:
            # DIRECT: skip local handlers (no next() call)
            logger.debug(
                f"Skipping local handlers for event '{ctx.event_type}' (policy: DIRECT)"
            )
            pass

    return dispatcher_middleware
