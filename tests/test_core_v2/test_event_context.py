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
Tests for EventContext
"""

import pytest
from krules_core.container import KRulesContainer
from krules_core import EventContext


# Global container and decorators for the test module
container = None
on = None
when = None
middleware = None
emit = None


@pytest.fixture(autouse=True)
def setup():
    """Create fresh container before each test"""
    global container, on, when, middleware, emit

    # Create new container for each test (isolation)
    container = KRulesContainer()

    # Get handlers from container
    on, when, middleware, emit = container.handlers()

    yield

    # Cleanup
    container = None


class TestEventContext:
    """Test suite for EventContext"""

    @pytest.mark.asyncio
    async def test_context_basic_attributes(self):
        """EventContext should expose event_type, subject, and payload"""
        contexts = []

        @on("test.event")
        async def handler(ctx: EventContext):
            contexts.append({
                "event_type": ctx.event_type,
                "subject": ctx.subject,
                "payload": ctx.payload
            })

        subject = container.subject("test-subject")
        payload = {"key": "value", "number": 42}

        await emit("test.event", subject, payload)

        assert len(contexts) == 1
        assert contexts[0]["event_type"] == "test.event"
        assert contexts[0]["subject"] is subject
        assert contexts[0]["payload"] == payload

    @pytest.mark.asyncio
    async def test_context_property_changed_auto_extraction(self):
        """EventContext should auto-extract property_name, old_value, new_value"""
        contexts = []

        @on("subject-property-changed")
        async def handler(ctx: EventContext):
            contexts.append({
                "property_name": ctx.property_name,
                "old_value": ctx.old_value,
                "new_value": ctx.new_value
            })

        subject = container.subject("test-subject")
        await subject.set("temperature", 75)
        await subject.set("temperature", 85)

        import asyncio
        await asyncio.sleep(0.01)

        # Should have 2 property changes
        assert len(contexts) == 2

        # First: None → 75
        assert contexts[0]["property_name"] == "temperature"
        assert contexts[0]["old_value"] is None
        assert contexts[0]["new_value"] == 75

        # Second: 75 → 85
        assert contexts[1]["property_name"] == "temperature"
        assert contexts[1]["old_value"] == 75
        assert contexts[1]["new_value"] == 85

    @pytest.mark.asyncio
    async def test_context_property_deleted_auto_extraction(self):
        """EventContext should auto-extract property_name and old_value for deletions"""
        contexts = []

        @on("subject-property-deleted")
        async def handler(ctx: EventContext):
            contexts.append({
                "property_name": ctx.property_name,
                "old_value": ctx.old_value,
                "new_value": ctx.new_value
            })

        subject = container.subject("test-subject")
        await subject.set("temp_token", "abc123")

        import asyncio
        await asyncio.sleep(0.01)

        await subject.delete("temp_token")

        await asyncio.sleep(0.01)

        # Should have 1 deletion
        assert len(contexts) == 1
        assert contexts[0]["property_name"] == "temp_token"
        assert contexts[0]["old_value"] == "abc123"
        assert contexts[0]["new_value"] is None  # No new_value for deletions

    @pytest.mark.asyncio
    async def test_context_emit_reuses_subject(self):
        """ctx.emit() should reuse current subject by default"""
        sequence = []

        @on("first.event")
        async def handler1(ctx: EventContext):
            sequence.append({
                "event": "first",
                "subject": ctx.subject.name
            })
            # Emit without specifying subject
            await ctx.emit("second.event", {"from": "first"})

        @on("second.event")
        async def handler2(ctx: EventContext):
            sequence.append({
                "event": "second",
                "subject": ctx.subject.name,
                "from": ctx.payload.get("from")
            })

        subject = container.subject("original-subject")
        await emit("first.event", subject)

        assert len(sequence) == 2
        # Both events should use the same subject
        assert sequence[0]["subject"] == "original-subject"
        assert sequence[1]["subject"] == "original-subject"
        assert sequence[1]["from"] == "first"

    @pytest.mark.asyncio
    async def test_context_emit_custom_subject(self):
        """ctx.emit() should allow overriding subject"""
        sequence = []

        @on("trigger.event")
        async def handler1(ctx: EventContext):
            sequence.append(ctx.subject.name)
            # Emit with different subject
            other_subject = container.subject("different-subject")
            await ctx.emit("target.event", subject=other_subject)

        @on("target.event")
        async def handler2(ctx: EventContext):
            sequence.append(ctx.subject.name)

        subject = container.subject("original-subject")
        await emit("trigger.event", subject)

        assert len(sequence) == 2
        assert sequence[0] == "original-subject"
        assert sequence[1] == "different-subject"

    @pytest.mark.asyncio
    async def test_context_metadata(self):
        """EventContext should support get/set_metadata for middleware communication"""
        metadata_log = []

        @middleware
        async def add_metadata_mw(ctx: EventContext, next):
            ctx.set_metadata("request_id", "req-123")
            ctx.set_metadata("timestamp", 1234567890)
            await next()

        @on("test.event")
        async def handler(ctx: EventContext):
            metadata_log.append({
                "request_id": ctx.get_metadata("request_id"),
                "timestamp": ctx.get_metadata("timestamp"),
                "missing": ctx.get_metadata("missing", "default")
            })

        subject = container.subject("test")
        await emit("test.event", subject)

        assert len(metadata_log) == 1
        assert metadata_log[0]["request_id"] == "req-123"
        assert metadata_log[0]["timestamp"] == 1234567890
        assert metadata_log[0]["missing"] == "default"

    @pytest.mark.asyncio
    async def test_context_metadata_from_extra_kwargs(self):
        """Extra kwargs in emit() should be stored in metadata"""
        metadata_log = []

        @on("test.event")
        async def handler(ctx: EventContext):
            metadata_log.append({
                "topic": ctx.get_metadata("topic"),
                "dataschema": ctx.get_metadata("dataschema"),
                "custom": ctx.get_metadata("custom_key")
            })

        subject = container.subject("test")
        await emit(
            "test.event",
            subject,
            {},
            topic="alerts",
            dataschema="http://example.com/schema",
            custom_key="custom_value"
        )

        assert len(metadata_log) == 1
        assert metadata_log[0]["topic"] == "alerts"
        assert metadata_log[0]["dataschema"] == "http://example.com/schema"
        assert metadata_log[0]["custom"] == "custom_value"

    @pytest.mark.asyncio
    async def test_context_payload_dict_access(self):
        """Payload keys must be accessed via ctx.payload dict, not as attributes"""
        contexts = []

        @on("test.event")
        async def handler(ctx: EventContext):
            # Access via dict
            ip = ctx.payload["ip"]
            user_agent = ctx.payload.get("user_agent")

            # Try to access as attribute (should fail)
            has_ip_attr = hasattr(ctx, "ip")

            contexts.append({
                "ip": ip,
                "user_agent": user_agent,
                "has_ip_attr": has_ip_attr
            })

        subject = container.subject("test")
        await emit("test.event", subject, {
            "ip": "1.2.3.4",
            "user_agent": "Mozilla/5.0"
        })

        assert len(contexts) == 1
        assert contexts[0]["ip"] == "1.2.3.4"
        assert contexts[0]["user_agent"] == "Mozilla/5.0"
        # Custom payload keys are NOT auto-extracted as attributes
        assert contexts[0]["has_ip_attr"] is False

    @pytest.mark.asyncio
    async def test_context_payload_isolation(self):
        """Verify payload behavior between handlers"""
        handler_payloads = []

        @on("shared.event")
        async def handler1(ctx: EventContext):
            # Record original
            handler_payloads.append({
                "handler": "handler1",
                "original": ctx.payload.copy()
            })
            # Modify payload
            ctx.payload["modified_by"] = "handler1"

        @on("shared.event")
        async def handler2(ctx: EventContext):
            # Check if modification from handler1 is visible
            handler_payloads.append({
                "handler": "handler2",
                "payload": ctx.payload.copy(),
                "has_modification": "modified_by" in ctx.payload
            })

        subject = container.subject("test")
        await emit("shared.event", subject, {"original_key": "value"})

        assert len(handler_payloads) == 2
        # Both handlers receive the same payload dict (shared reference)
        assert handler_payloads[1]["has_modification"] is True
        assert handler_payloads[1]["payload"]["modified_by"] == "handler1"

    @pytest.mark.asyncio
    async def test_context_emit_with_payload(self):
        """ctx.emit() should support custom payload"""
        events = []

        @on("trigger")
        async def handler1(ctx: EventContext):
            events.append({
                "event": "trigger",
                "payload": ctx.payload
            })
            await ctx.emit("result", {"status": "success", "count": 42})

        @on("result")
        async def handler2(ctx: EventContext):
            events.append({
                "event": "result",
                "payload": ctx.payload
            })

        subject = container.subject("test")
        await emit("trigger", subject, {"input": "data"})

        assert len(events) == 2
        assert events[0]["payload"] == {"input": "data"}
        assert events[1]["payload"] == {"status": "success", "count": 42}
