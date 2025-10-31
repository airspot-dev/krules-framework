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
Integration tests for CloudEvents HTTP dispatcher end-to-end flow.
"""

import pytest
from unittest.mock import Mock, patch
from krules_cloudevents import (
    CloudEventsDispatcher,
    create_dispatcher_middleware,
    DispatchPolicyConst,
)
from krules_core import EventContext


class TestCloudEventsIntegration:
    """Integration tests for CloudEvents HTTP dispatcher."""

    @pytest.mark.asyncio
    async def test_emit_with_dispatch_url(self, container):
        """Test transparent emit() with dispatch_url triggers external dispatch."""
        # Setup dispatcher and middleware
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="order-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(middleware_func)

        # Get handlers
        on, when, middleware, emit = container.handlers()

        # Track local handler execution
        handler_called = False

        @on("order.created")
        async def handle_order(ctx: EventContext):
            nonlocal handler_called
            handler_called = True

        # Emit with dispatch_url (DIRECT policy - no local handlers)
        subject = container.subject("order-123")

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await emit(
                "order.created",
                subject,
                {"amount": 100.0},
                dispatch_url="https://api.example.com/orders",
            )

            # Verify external dispatch happened
            mock_dispatch.assert_called_once()
            assert mock_dispatch.call_args.kwargs["event_type"] == "order.created"

            # Verify local handler NOT called (DIRECT policy)
            assert not handler_called

    @pytest.mark.asyncio
    async def test_emit_with_both_policy(self, container):
        """Test BOTH policy dispatches externally AND executes local handlers."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="order-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(middleware_func)

        on, when, middleware, emit = container.handlers()

        handler_called = False

        @on("order.created")
        async def handle_order(ctx: EventContext):
            nonlocal handler_called
            handler_called = True

        subject = container.subject("order-123")

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await emit(
                "order.created",
                subject,
                {"amount": 100.0},
                dispatch_url="https://api.example.com/orders",
                dispatch_policy=DispatchPolicyConst.BOTH,
            )

            # Verify both external dispatch AND local handler
            mock_dispatch.assert_called_once()
            assert handler_called

    @pytest.mark.asyncio
    async def test_emit_without_dispatch_url(self, container):
        """Test normal emit without dispatch_url only triggers local handlers."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="order-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(middleware_func)

        on, when, middleware, emit = container.handlers()

        handler_called = False

        @on("order.created")
        async def handle_order(ctx: EventContext):
            nonlocal handler_called
            handler_called = True

        subject = container.subject("order-123")

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            # Normal emit (no dispatch_url)
            await emit("order.created", subject, {"amount": 100.0})

            # Verify NO external dispatch
            mock_dispatch.assert_not_called()

            # Verify local handler WAS called
            assert handler_called

    @pytest.mark.asyncio
    async def test_context_emit_in_handler(self, container):
        """Test ctx.emit() with dispatch_url inside a handler."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="order-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(middleware_func)

        on, when, middleware, emit = container.handlers()

        notification_sent = False

        @on("order.created")
        async def handle_order(ctx: EventContext):
            # Validate order
            ctx.subject.set("validated", True)

            # Send notification to external service
            await ctx.emit(
                "notification.send",
                ctx.subject,
                {"type": "email", "template": "order_confirmation"},
                dispatch_url="https://notification-service.example.com/send",
            )

        @on("notification.send")
        async def handle_notification(ctx: EventContext):
            nonlocal notification_sent
            notification_sent = True

        subject = container.subject("order-456")

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            # Trigger order creation
            await emit("order.created", subject, {"amount": 200.0})

            # Verify notification was dispatched externally
            mock_dispatch.assert_called_once()
            assert mock_dispatch.call_args.kwargs["event_type"] == "notification.send"

            # Verify notification handler NOT called (DIRECT policy)
            assert not notification_sent

    @pytest.mark.asyncio
    async def test_dynamic_dispatch_url(self, container):
        """Test dynamic dispatch URL based on event type."""
        def get_dispatch_url(subject, event_type):
            if event_type.startswith("order."):
                return "https://order-service.example.com/events"
            elif event_type.startswith("payment."):
                return "https://payment-service.example.com/events"
            return "https://api.example.com/events"

        dispatcher = CloudEventsDispatcher(
            dispatch_url=get_dispatch_url,
            source="gateway-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)
        container.event_bus().add_middleware(middleware_func)

        on, when, middleware, emit = container.handlers()

        subject = container.subject("transaction-789")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            # Emit order event
            await emit(
                "order.confirmed",
                subject,
                {"amount": 300.0},
                dispatch_url=True,  # Trigger dispatch with default callable URL
            )

            # Note: Since dispatch_url is True (not a string), middleware won't trigger
            # This test demonstrates callable dispatch_url in direct dispatch() call

        # Test direct dispatch with callable URL
        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="payment.processed",
                subject=subject,
                payload={"amount": 300.0},
            )

            # Verify URL was generated dynamically
            call_args = mock_post.call_args
            assert "payment-service" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_multi_service_event_chain(self, container):
        """Test event chain across services (simulated)."""
        # Service A: Order Service
        order_service_container = container

        order_dispatcher = CloudEventsDispatcher(
            dispatch_url="https://inventory-service.example.com/events",
            source="order-service",
            krules_container=order_service_container,
        )
        order_mw = create_dispatcher_middleware(order_dispatcher)
        order_service_container.event_bus().add_middleware(order_mw)

        on, when, middleware, emit = order_service_container.handlers()

        dispatched_events = []

        # Register a no-op handler for inventory.check so middleware runs
        # (middleware only runs when there are matching handlers)
        @on("inventory.check")
        async def inventory_handler(ctx: EventContext):
            pass  # This would normally be in the inventory service

        @on("order.placed")
        async def process_order(ctx: EventContext):
            # Validate order
            ctx.subject.set("status", "validated")

            # Request inventory check from inventory service
            await ctx.emit(
                "inventory.check",
                {"items": ["item-1", "item-2"]},
                ctx.subject,
                dispatch_url="https://inventory-service.example.com/check",
            )

        # Patch dispatcher before emitting
        with patch.object(order_dispatcher, "dispatch") as mock_dispatch:
            # Simulate order placement
            order_subject = order_service_container.subject("order-999")
            await emit("order.placed", order_subject, {"total": 500.0})

            # Track dispatched events
            if mock_dispatch.called:
                for call in mock_dispatch.call_args_list:
                    dispatched_events.append(call.kwargs["event_type"])

        # Verify inventory check was dispatched
        assert len(dispatched_events) == 1
        assert dispatched_events[0] == "inventory.check"

    @pytest.mark.asyncio
    async def test_originid_preserved_across_events(self, container):
        """Test that originid is preserved through event chain."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )

        # Create subject with originid
        subject = container.subject(
            "chain-subject",
            event_info={"originid": "root-event-123"}
        )

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            # Dispatch event
            event_id = dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
            )

            # Verify originid in headers
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-originid"] == "root-event-123"
            assert headers["ce-id"] == event_id
            assert headers["ce-id"] != headers["ce-originid"]  # Different IDs

    @pytest.mark.asyncio
    async def test_extended_properties_in_dispatch(self, container):
        """Test that subject extended properties are dispatched."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("tenant-resource")
        subject.set_ext("tenant_id", "tenant-abc")
        subject.set_ext("environment", "production")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="resource.updated",
                subject=subject,
                payload={"changes": ["field1", "field2"]},
            )

            # Verify extended properties in headers
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-tenant_id"] == "tenant-abc"
            assert headers["ce-environment"] == "production"
