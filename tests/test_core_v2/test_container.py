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
Tests for KRulesContainer (Dependency Injection)
"""

import pytest
from dependency_injector import providers
from krules_core.container import KRulesContainer
from krules_core.event_bus import EventBus
from krules_core.subject.storaged_subject import Subject
from krules_core import EventContext


class TestKRulesContainer:
    """Test suite for KRulesContainer dependency injection"""

    def test_container_provides_event_bus_singleton(self):
        """event_bus() should return singleton instance"""
        container = KRulesContainer()

        bus1 = container.event_bus()
        bus2 = container.event_bus()

        # Should be same instance
        assert bus1 is bus2
        assert isinstance(bus1, EventBus)

    def test_container_provides_subject_factory(self):
        """subject() should create new Subject instances (Factory, not Singleton)"""
        container = KRulesContainer()

        subject1 = container.subject("user-123")
        subject2 = container.subject("user-123")

        # Factory creates new instances each time
        assert subject1 is not subject2
        assert isinstance(subject1, Subject)
        assert isinstance(subject2, Subject)
        assert subject1.name == "user-123"
        assert subject2.name == "user-123"

    def test_subject_has_injected_dependencies(self):
        """Subject should have storage and event_bus injected from container"""
        container = KRulesContainer()
        subject = container.subject("test-subject")

        # Subject should have event_bus from container
        assert subject._event_bus is container.event_bus()

        # Subject should have storage (callable was injected)
        assert subject._storage is not None

    def test_multiple_containers_isolated(self):
        """Different containers should have isolated event buses"""
        container1 = KRulesContainer()
        container2 = KRulesContainer()

        bus1 = container1.event_bus()
        bus2 = container2.event_bus()

        # Different containers = different event buses
        assert bus1 is not bus2

    @pytest.mark.asyncio
    async def test_container_handlers_work(self):
        """handlers() should return functional decorators bound to event bus"""
        container = KRulesContainer()
        on, when, middleware, emit = container.handlers()

        events = []

        @on("test.event")
        async def handler(ctx: EventContext):
            events.append(ctx.event_type)

        subject = container.subject("test")
        await emit("test.event", subject)

        assert len(events) == 1
        assert events[0] == "test.event"

    @pytest.mark.asyncio
    async def test_handlers_bound_to_container_event_bus(self):
        """Handlers should use container's event bus (not separate instance)"""
        container = KRulesContainer()
        on, when, middleware, emit = container.handlers()

        events = []

        @on("test.event")
        async def handler(ctx: EventContext):
            events.append("handled")

        # Emit via container's event bus directly
        subject = container.subject("test")
        await container.event_bus().emit("test.event", subject, {})

        assert len(events) == 1
        assert events[0] == "handled"

    @pytest.mark.asyncio
    async def test_containers_isolated_event_handlers(self):
        """Events in container A should not trigger handlers in container B"""
        container1 = KRulesContainer()
        container2 = KRulesContainer()

        on1, _, _, emit1 = container1.handlers()
        on2, _, _, emit2 = container2.handlers()

        events1 = []
        events2 = []

        @on1("test.event")
        async def handler1(ctx: EventContext):
            events1.append("container1")

        @on2("test.event")
        async def handler2(ctx: EventContext):
            events2.append("container2")

        # Emit in container1
        subject1 = container1.subject("test")
        await emit1("test.event", subject1)

        # Only container1 handler should fire
        assert len(events1) == 1
        assert len(events2) == 0

        # Emit in container2
        subject2 = container2.subject("test")
        await emit2("test.event", subject2)

        # Now container2 handler fires
        assert len(events1) == 1  # Still 1
        assert len(events2) == 1

    def test_container_default_storage_is_empty(self):
        """Default subject storage should be EmptySubjectStorage"""
        container = KRulesContainer()
        subject = container.subject("test")

        # EmptySubjectStorage characteristics
        assert subject._storage.is_persistent() is False
        assert subject._storage.is_concurrency_safe() is False

    def test_container_storage_override(self):
        """Container should support storage override for testing"""
        # Create mock storage factory
        class MockStorage:
            def __init__(self, name, **kwargs):
                self.name = name
                self.mock_marker = "mocked"

            def is_persistent(self):
                return True

            def is_concurrency_safe(self):
                return True

            def load(self):
                return {}, {}

            def store(self, inserts=[], updates=[], deletes=[]):
                pass

            def set(self, prop, old_value_default=None):
                return None, None

            def get(self, prop):
                raise AttributeError(prop)

            def delete(self, prop):
                pass

            def get_ext_props(self):
                return {}

            def flush(self):
                return self

        # Create factory function (like create_empty_storage)
        def create_mock_storage():
            def storage_factory(name, **kwargs):
                return MockStorage(name, **kwargs)
            return storage_factory

        container = KRulesContainer()

        # Override storage
        container.subject_storage.override(providers.Callable(create_mock_storage))

        subject = container.subject("test-subject")

        # Should use mocked storage
        assert hasattr(subject._storage, "mock_marker")
        assert subject._storage.mock_marker == "mocked"
        assert subject._storage.is_persistent() is True

    def test_container_storage_override_context_manager(self):
        """Storage override with context manager should be temporary"""
        class MockStorage:
            def __init__(self, name, **kwargs):
                self.mock_marker = "mocked"

            def is_persistent(self):
                return True

            def is_concurrency_safe(self):
                return False

            def load(self):
                return {}, {}

            def store(self, inserts=[], updates=[], deletes=[]):
                pass

            def set(self, prop, old_value_default=None):
                return None, None

            def get(self, prop):
                raise AttributeError(prop)

            def delete(self, prop):
                pass

            def get_ext_props(self):
                return {}

            def flush(self):
                return self

        def create_mock_storage():
            def storage_factory(name, **kwargs):
                return MockStorage(name, **kwargs)
            return storage_factory

        container = KRulesContainer()

        # Before override - default storage
        subject_before = container.subject("before")
        assert not hasattr(subject_before._storage, "mock_marker")

        # With override - mock storage
        with container.subject_storage.override(providers.Callable(create_mock_storage)):
            subject_during = container.subject("during")
            assert hasattr(subject_during._storage, "mock_marker")
            assert subject_during._storage.mock_marker == "mocked"

        # After override - back to default
        subject_after = container.subject("after")
        assert not hasattr(subject_after._storage, "mock_marker")

    def test_handlers_returns_tuple(self):
        """handlers() should return (on, when, middleware, emit) tuple"""
        container = KRulesContainer()
        result = container.handlers()

        assert isinstance(result, tuple)
        assert len(result) == 4

        on, when, middleware, emit = result

        # All should be callable
        assert callable(on)
        assert callable(when)
        assert callable(middleware)
        assert callable(emit)

    def test_multiple_handlers_calls_same_event_bus(self):
        """Multiple handlers() calls should use same event bus (singleton)"""
        container = KRulesContainer()

        on1, _, _, emit1 = container.handlers()
        on2, _, _, emit2 = container.handlers()

        # Different decorator instances but bound to same event bus
        # Verify by checking they share handlers registry

        events = []

        @on1("test.event")
        async def handler1(ctx: EventContext):
            events.append("handler1")

        @on2("test.event")
        async def handler2(ctx: EventContext):
            events.append("handler2")

        # Both handlers should be registered on the same event bus
        bus = container.event_bus()
        assert len(bus._handlers) == 2

    @pytest.mark.asyncio
    async def test_subject_operations_emit_events_on_container_bus(self):
        """Subject property changes should emit events on container's event bus"""
        container = KRulesContainer()
        on, _, _, emit = container.handlers()

        changes = []

        @on("subject-property-changed")
        async def handler(ctx: EventContext):
            changes.append(ctx.property_name)

        subject = container.subject("test")
        subject.set("temperature", 75)

        # Give async events time to process
        import asyncio
        await asyncio.sleep(0.01)

        # Event should have been received
        assert len(changes) == 1
        assert changes[0] == "temperature"
