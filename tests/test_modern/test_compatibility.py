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
Tests to verify backward compatibility between modern and legacy APIs.

These tests ensure that:
1. Modern handlers work with existing Subject class
2. Modern and legacy rules can coexist
3. Events route correctly between both systems
4. Storage and event emission remain compatible
"""

import pytest
from datetime import datetime

from krules_core.providers import (
    subject_factory,
    event_router_factory,
    subject_storage_factory,
    event_dispatcher_factory,
)
from krules_core.subject.empty_storage import EmptySubjectStorage
from krules_core.route.router import EventRouter
from krules_core.route.dispatcher import BaseDispatcher
from krules_core.core import RuleFactory
from krules_core import event_types

# Modern API imports
from krules_core.modern import on, when, EventContext, register_modern_handlers


@pytest.fixture(autouse=True)
def setup_environment():
    """Reset environment before each test"""
    # Override with fresh instances
    from dependency_injector import providers

    subject_storage_factory.override(
        providers.Factory(lambda *args, **kwargs: EmptySubjectStorage())
    )
    event_router_factory.override(providers.Singleton(lambda: EventRouter()))
    event_dispatcher_factory.override(providers.Singleton(lambda: BaseDispatcher()))

    # Clear any registered rules
    router = event_router_factory()
    router.unregister_all()

    yield

    # Cleanup
    router.unregister_all()


def test_modern_handler_works_with_existing_subject():
    """Modern handlers should work with existing dynamic Subject"""
    results = []

    @on("test.event")
    async def handler(ctx: EventContext):
        # Should work with existing Subject class
        subject = ctx.subject
        subject.set("processed", True)
        subject.set("timestamp", datetime.now())
        results.append(ctx.event_type)

    # Register modern handlers as legacy rules
    register_modern_handlers()

    # Use existing subject_factory
    subject = subject_factory("test-subject")
    subject.set("initial", "value")

    # Route event through existing router
    router = event_router_factory()
    router.route("test.event", subject, {})

    # Verify handler executed
    assert len(results) == 1
    assert results[0] == "test.event"
    assert subject.get("processed") == True
    assert subject.get("initial") == "value"


def test_modern_and_legacy_coexist():
    """Modern handlers and legacy rules should work together"""
    modern_called = []
    legacy_called = []

    # Modern handler
    @on("user.login")
    async def modern_handler(ctx: EventContext):
        ctx.subject.set("modern", True)
        modern_called.append(True)

    register_modern_handlers()

    # Legacy rule
    from krules_core.base_functions.processing import SetSubjectProperty

    RuleFactory.create(
        name="legacy-rule",
        subscribe_to="user.login",
        data={
            "processing": [
                SetSubjectProperty("legacy", lambda: True),
                SetSubjectProperty("_marker", lambda: legacy_called.append(True) or True)
            ]
        }
    )

    # Route event
    subject = subject_factory("user-123")
    router = event_router_factory()
    router.route("user.login", subject, {})

    # Both should execute
    assert len(modern_called) == 1
    assert len(legacy_called) == 1
    assert subject.get("modern") == True
    assert subject.get("legacy") == True


def test_property_change_events_work_with_modern():
    """Property changes should trigger modern handlers"""
    changes = []

    @on(event_types.SUBJECT_PROPERTY_CHANGED)
    @when(lambda ctx: ctx.property_name == "temperature")
    async def on_temp_change(ctx: EventContext):
        changes.append({
            "old": ctx.old_value,
            "new": ctx.new_value
        })

    register_modern_handlers()

    # Change property (triggers event automatically)
    subject = subject_factory("device-123")
    subject.set("temperature", 75)
    subject.set("temperature", 85)

    # Should have captured both changes
    assert len(changes) == 2
    assert changes[0]["new"] == 75
    assert changes[1]["old"] == 75
    assert changes[1]["new"] == 85


def test_filters_work_correctly():
    """@when filters should prevent execution when conditions fail"""
    executed = []

    @on("test.filtered")
    @when(lambda ctx: ctx.payload.get("allowed") == True)
    async def filtered_handler(ctx: EventContext):
        executed.append(True)

    register_modern_handlers()

    router = event_router_factory()
    subject = subject_factory("test")

    # Should NOT execute (filter fails)
    router.route("test.filtered", subject, {"allowed": False})
    assert len(executed) == 0

    # Should execute (filter passes)
    router.route("test.filtered", subject, {"allowed": True})
    assert len(executed) == 1


def test_multiple_filters_all_must_pass():
    """Multiple @when decorators should require ALL to pass"""
    executed = []

    @on("test.multi")
    @when(lambda ctx: ctx.payload.get("check1") == True)
    @when(lambda ctx: ctx.payload.get("check2") == True)
    async def multi_filter_handler(ctx: EventContext):
        executed.append(True)

    register_modern_handlers()

    router = event_router_factory()
    subject = subject_factory("test")

    # Only one passes
    router.route("test.multi", subject, {"check1": True, "check2": False})
    assert len(executed) == 0

    # Both pass
    router.route("test.multi", subject, {"check1": True, "check2": True})
    assert len(executed) == 1


def test_glob_patterns_work():
    """Event pattern matching with glob should work"""
    device_events = []
    user_events = []

    @on("device.*")
    async def handle_device(ctx: EventContext):
        device_events.append(ctx.event_type)

    @on("user.*")
    async def handle_user(ctx: EventContext):
        user_events.append(ctx.event_type)

    register_modern_handlers()

    router = event_router_factory()
    subject = subject_factory("test")

    router.route("device.created", subject, {})
    router.route("device.updated", subject, {})
    router.route("user.login", subject, {})

    assert len(device_events) == 2
    assert "device.created" in device_events
    assert "device.updated" in device_events
    assert len(user_events) == 1
    assert "user.login" in user_events


def test_context_emit_creates_new_events():
    """ctx.emit() should trigger other handlers"""
    events_sequence = []

    @on("first")
    async def first_handler(ctx: EventContext):
        events_sequence.append("first")
        await ctx.emit("second", {"from": "first"})

    @on("second")
    async def second_handler(ctx: EventContext):
        events_sequence.append("second")
        assert ctx.payload.get("from") == "first"

    register_modern_handlers()

    router = event_router_factory()
    subject = subject_factory("test")
    router.route("first", subject, {})

    assert events_sequence == ["first", "second"]


def test_existing_storage_compatibility():
    """Modern API should work with any storage backend"""
    # This uses EmptySubjectStorage but should work with Redis, SQLite, etc.
    @on("storage.test")
    async def handler(ctx: EventContext):
        subject = ctx.subject
        subject.set("key1", "value1")
        subject.set("key2", 123)
        subject.set("key3", {"nested": "data"})

    register_modern_handlers()

    subject = subject_factory("storage-test")
    router = event_router_factory()
    router.route("storage.test", subject, {})

    # Values should be stored (even in EmptyStorage they're in memory)
    assert subject.get("key1") == "value1"
    assert subject.get("key2") == 123
    assert subject.get("key3") == {"nested": "data"}


def test_sync_handlers_also_work():
    """Non-async handlers should also work"""
    results = []

    @on("sync.test")
    def sync_handler(ctx: EventContext):  # Not async!
        results.append(ctx.event_type)
        ctx.subject.set("sync", True)

    register_modern_handlers()

    router = event_router_factory()
    subject = subject_factory("test")
    router.route("sync.test", subject, {})

    assert len(results) == 1
    assert subject.get("sync") == True