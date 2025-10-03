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
Tests for KRules 2.0 event bus and handlers
"""

import pytest
from datetime import datetime

from krules_core import (
    on,
    when,
    middleware,
    emit,
    subject_factory,
    EventContext,
    reset_event_bus,
)
from krules_core.providers import subject_storage_factory
from krules_core.subject.empty_storage import EmptySubjectStorage
from dependency_injector import providers


@pytest.fixture(autouse=True)
def setup():
    """Reset event bus and storage before each test"""
    reset_event_bus()
    subject_storage_factory.override(
        providers.Factory(lambda *args, **kwargs: EmptySubjectStorage())
    )
    yield


@pytest.mark.asyncio
async def test_basic_handler():
    """Basic event handler should execute"""
    results = []

    @on("test.event")
    async def handler(ctx: EventContext):
        results.append(ctx.event_type)

    subject = subject_factory("test")
    await emit("test.event", subject)

    assert len(results) == 1
    assert results[0] == "test.event"


@pytest.mark.asyncio
async def test_handler_with_filter():
    """Handlers with @when filter should only execute when condition passes"""
    executed = []

    @on("test.filtered")
    @when(lambda ctx: ctx.payload.get("allowed") == True)
    async def handler(ctx: EventContext):
        executed.append(True)

    subject = subject_factory("test")

    # Filter fails
    await emit("test.filtered", subject, {"allowed": False})
    assert len(executed) == 0

    # Filter passes
    await emit("test.filtered", subject, {"allowed": True})
    assert len(executed) == 1


@pytest.mark.asyncio
async def test_multiple_filters():
    """Multiple @when decorators should all need to pass"""
    executed = []

    @on("test.multi")
    @when(lambda ctx: ctx.payload.get("check1") == True)
    @when(lambda ctx: ctx.payload.get("check2") == True)
    async def handler(ctx: EventContext):
        executed.append(True)

    subject = subject_factory("test")

    await emit("test.multi", subject, {"check1": True, "check2": False})
    assert len(executed) == 0

    await emit("test.multi", subject, {"check1": True, "check2": True})
    assert len(executed) == 1


@pytest.mark.asyncio
async def test_glob_patterns():
    """Glob patterns should match multiple events"""
    events = []

    @on("user.*")
    async def handler(ctx: EventContext):
        events.append(ctx.event_type)

    subject = subject_factory("test")

    await emit("user.created", subject)
    await emit("user.updated", subject)
    await emit("user.deleted", subject)
    await emit("device.created", subject)  # Should not match

    assert len(events) == 3
    assert "user.created" in events
    assert "user.updated" in events
    assert "user.deleted" in events


@pytest.mark.asyncio
async def test_wildcard_handler():
    """Wildcard (*) should match all events"""
    all_events = []

    @on("*")
    async def handler(ctx: EventContext):
        all_events.append(ctx.event_type)

    subject = subject_factory("test")

    await emit("event1", subject)
    await emit("event2", subject)
    await emit("event3", subject)

    assert len(all_events) == 3


@pytest.mark.asyncio
async def test_subject_property_changes_emit_events():
    """Subject property changes should automatically emit events"""
    changes = []

    @on("subject-property-changed")
    async def handler(ctx: EventContext):
        changes.append({
            "property": ctx.property_name,
            "old": ctx.old_value,
            "new": ctx.new_value
        })

    subject = subject_factory("device-123")
    subject.set("temperature", 75)
    subject.set("temperature", 85)

    # Give async events time to process
    import asyncio
    await asyncio.sleep(0.01)

    assert len(changes) == 2
    assert changes[0]["property"] == "temperature"
    assert changes[0]["old"] is None
    assert changes[0]["new"] == 75
    assert changes[1]["old"] == 75
    assert changes[1]["new"] == 85


@pytest.mark.asyncio
async def test_property_change_filtering():
    """Can filter property change events by property name"""
    temp_changes = []
    status_changes = []

    @on("subject-property-changed")
    @when(lambda ctx: ctx.property_name == "temperature")
    async def on_temp(ctx: EventContext):
        temp_changes.append(ctx.new_value)

    @on("subject-property-changed")
    @when(lambda ctx: ctx.property_name == "status")
    async def on_status(ctx: EventContext):
        status_changes.append(ctx.new_value)

    subject = subject_factory("device")
    subject.set("temperature", 75)
    subject.set("status", "ok")
    subject.set("temperature", 85)

    import asyncio
    await asyncio.sleep(0.01)

    assert len(temp_changes) == 2
    assert temp_changes == [75, 85]
    assert len(status_changes) == 1
    assert status_changes == ["ok"]


@pytest.mark.asyncio
async def test_context_emit_triggers_handlers():
    """ctx.emit() should trigger other handlers"""
    sequence = []

    @on("first")
    async def first(ctx: EventContext):
        sequence.append("first")
        await ctx.emit("second", {"from": "first"})

    @on("second")
    async def second(ctx: EventContext):
        sequence.append("second")
        assert ctx.payload["from"] == "first"
        await ctx.emit("third")

    @on("third")
    async def third(ctx: EventContext):
        sequence.append("third")

    subject = subject_factory("test")
    await emit("first", subject)

    assert sequence == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_sync_handlers():
    """Non-async handlers should also work"""
    results = []

    @on("sync.event")
    def sync_handler(ctx: EventContext):
        results.append("sync")
        ctx.subject.set("value", 42)

    subject = subject_factory("test")
    await emit("sync.event", subject)

    assert len(results) == 1
    assert subject.get("value") == 42


@pytest.mark.asyncio
async def test_middleware():
    """Middleware should run for all events"""
    middleware_called = []
    handler_called = []

    @middleware
    async def log_middleware(ctx: EventContext, next):
        middleware_called.append(f"before-{ctx.event_type}")
        await next()
        middleware_called.append(f"after-{ctx.event_type}")

    @on("test.event")
    async def handler(ctx: EventContext):
        handler_called.append(True)

    subject = subject_factory("test")
    await emit("test.event", subject)

    assert len(middleware_called) == 2
    assert middleware_called[0] == "before-test.event"
    assert middleware_called[1] == "after-test.event"
    assert len(handler_called) == 1


@pytest.mark.asyncio
async def test_multiple_handlers_same_event():
    """Multiple handlers can listen to the same event"""
    results = []

    @on("shared.event")
    async def handler1(ctx: EventContext):
        results.append("handler1")

    @on("shared.event")
    async def handler2(ctx: EventContext):
        results.append("handler2")

    @on("shared.event")
    async def handler3(ctx: EventContext):
        results.append("handler3")

    subject = subject_factory("test")
    await emit("shared.event", subject)

    assert len(results) == 3
    assert "handler1" in results
    assert "handler2" in results
    assert "handler3" in results


@pytest.mark.asyncio
async def test_subject_lambda_values():
    """Subject.set() should support lambda functions"""
    subject = subject_factory("counter")
    subject.set("count", 0)
    subject.set("count", lambda c: c + 1)
    subject.set("count", lambda c: c + 1)

    assert subject.get("count") == 2


@pytest.mark.asyncio
async def test_reusable_filters():
    """Filters can be reused across handlers"""
    executed = []

    def is_admin(ctx: EventContext) -> bool:
        return ctx.payload.get("role") == "admin"

    def is_active(ctx: EventContext) -> bool:
        return ctx.subject.get("status", "inactive") == "active"

    @on("action.execute")
    @when(is_admin)
    @when(is_active)
    async def admin_action(ctx: EventContext):
        executed.append("admin")

    subject = subject_factory("user-123")
    subject.set("status", "active")

    # Not admin
    await emit("action.execute", subject, {"role": "user"})
    assert len(executed) == 0

    # Admin but inactive
    subject.set("status", "inactive")
    await emit("action.execute", subject, {"role": "admin"})
    assert len(executed) == 0

    # Admin and active
    subject.set("status", "active")
    await emit("action.execute", subject, {"role": "admin"})
    assert len(executed) == 1