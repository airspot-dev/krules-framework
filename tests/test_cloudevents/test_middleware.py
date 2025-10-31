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
Tests for CloudEvents dispatcher middleware.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from krules_cloudevents import (
    CloudEventsDispatcher,
    create_dispatcher_middleware,
    DispatchPolicyConst,
)
from krules_core import EventContext


class TestDispatcherMiddleware:
    """Tests for CloudEvents dispatcher middleware."""

    @pytest.mark.asyncio
    async def test_middleware_skips_without_dispatch_url(self, container):
        """Test that middleware skips dispatch if no dispatch_url in metadata."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        # Create context without dispatch_url
        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        # Execute middleware
        await middleware_func(ctx, mock_next)

        # Verify next() was called (local handlers executed)
        assert next_called

    @pytest.mark.asyncio
    async def test_middleware_dispatch_direct_policy(self, container):
        """Test DIRECT policy: dispatch externally, skip local handlers."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify dispatch was called
            mock_dispatch.assert_called_once()
            assert mock_dispatch.call_args.kwargs["event_type"] == "test.event"

            # Verify next() was NOT called (DIRECT policy)
            assert not next_called

            # Verify metadata
            assert ctx.get_metadata("_dispatch_executed") is True
            assert ctx.get_metadata("_dispatched") is True

    @pytest.mark.asyncio
    async def test_middleware_dispatch_both_policy(self, container):
        """Test BOTH policy: dispatch externally AND execute local handlers."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dispatch_policy", DispatchPolicyConst.BOTH)

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify dispatch was called
            mock_dispatch.assert_called_once()

            # Verify next() WAS called (BOTH policy)
            assert next_called

    @pytest.mark.asyncio
    async def test_middleware_dispatch_only_once(self, container):
        """Test that dispatch happens only once per event (guard flag)."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")

        async def mock_next():
            pass

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            # First call - should dispatch
            await middleware_func(ctx, mock_next)
            assert mock_dispatch.call_count == 1

            # Second call - should skip dispatch
            await middleware_func(ctx, mock_next)
            assert mock_dispatch.call_count == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_middleware_dispatch_error_continues(self, container):
        """Test that dispatch errors don't prevent local handler execution."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dispatch_policy", DispatchPolicyConst.BOTH)

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            mock_dispatch.side_effect = Exception("Network error")

            # Should not raise, just log
            await middleware_func(ctx, mock_next)

            # Verify next() was still called
            assert next_called

            # Verify error is tracked in metadata
            assert ctx.get_metadata("_dispatch_error") == "Network error"

    @pytest.mark.asyncio
    async def test_middleware_legacy_always_policy(self, container):
        """Test legacy ALWAYS policy maps to BOTH."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dispatch_policy", DispatchPolicyConst.ALWAYS)

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify both dispatch and next() called (BOTH behavior)
            mock_dispatch.assert_called_once()
            assert next_called

    @pytest.mark.asyncio
    async def test_middleware_legacy_never_policy(self, container):
        """Test legacy NEVER policy skips dispatch."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dispatch_policy", DispatchPolicyConst.NEVER)

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify NO dispatch, only local handlers
            mock_dispatch.assert_not_called()
            assert next_called

    @pytest.mark.asyncio
    async def test_middleware_legacy_default_policy(self, container):
        """Test legacy DEFAULT policy maps to DIRECT."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dispatch_policy", DispatchPolicyConst.DEFAULT)

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify dispatch called, next() NOT called (DIRECT behavior)
            mock_dispatch.assert_called_once()
            assert not next_called

    @pytest.mark.asyncio
    async def test_middleware_invalid_policy_fallback(self, container):
        """Test invalid policy falls back to DIRECT."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dispatch_policy", "invalid_policy")

        next_called = False

        async def mock_next():
            nonlocal next_called
            next_called = True

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify dispatch called, next() NOT called (DIRECT fallback)
            mock_dispatch.assert_called_once()
            assert not next_called

    @pytest.mark.asyncio
    async def test_middleware_metadata_passthrough(self, container):
        """Test that optional metadata is passed to dispatcher."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url="https://api.example.com/events",
            source="test-service",
            krules_container=container,
        )
        middleware_func = create_dispatcher_middleware(dispatcher)

        subject = container.subject("test-subject")
        ctx = EventContext(
            event_type="test.event",
            subject=subject,
            payload={"data": "test"},
            _event_bus=container.event_bus()
        )
        ctx.set_metadata("dispatch_url", "https://api.example.com/events")
        ctx.set_metadata("dataschema", "https://schema.example.com/event.json")

        async def mock_next():
            pass

        with patch.object(dispatcher, "dispatch") as mock_dispatch:
            await middleware_func(ctx, mock_next)

            # Verify dataschema was passed through
            call_kwargs = mock_dispatch.call_args.kwargs
            assert call_kwargs["dataschema"] == "https://schema.example.com/event.json"
