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
Tests for async Subject system in KRules 3.0

All tests are async and use the new async API:
- await subject.set()
- await subject.get()
- await subject.has()
- await subject.keys()
"""

import pytest
from krules_core.container import KRulesContainer
from dependency_injector import providers
from tests.test_subject.test_storage_helper import create_test_storage, InMemoryTestStorage


# Global container for the test module
container = None


@pytest.fixture(autouse=True)
def setup():
    """Create fresh container before each test"""
    global container

    # Create new container for each test (isolation)
    container = KRulesContainer()

    # Override storage with test storage for use_cache tests
    container.subject_storage.override(providers.Object(create_test_storage()))

    yield

    # Cleanup
    InMemoryTestStorage.clear_all()
    container = None


@pytest.mark.asyncio
class TestSubjectAsync:
    """Test suite for async Subject"""

    async def test_subject_dynamic_properties(self):
        """Subject should support dynamic properties"""
        subject = container.subject("test-subject")

        await subject.set("name", "John")
        await subject.set("age", 30)
        await subject.set("active", True)

        assert await subject.get("name") == "John"
        assert await subject.get("age") == 30
        assert await subject.get("active") is True

    async def test_subject_lambda_values(self):
        """Subject.set() should support lambda for computed values"""
        subject = container.subject("counter")

        await subject.set("count", 0)
        await subject.set("count", lambda c: c + 1)
        await subject.set("count", lambda c: c + 1)
        await subject.set("count", lambda c: c + 1)

        assert await subject.get("count") == 3

    async def test_subject_default_values(self):
        """Subject.get() should support default values"""
        subject = container.subject("test")

        # Property doesn't exist - should return default
        value = await subject.get("missing", default="default-value")
        assert value == "default-value"

        # Property doesn't exist - should return None when default=None
        value = await subject.get("missing", default=None)
        assert value is None

        # Property doesn't exist - should raise without default
        with pytest.raises(AttributeError):
            await subject.get("missing")

    async def test_subject_extended_properties(self):
        """Subject should support extended properties"""
        subject = container.subject("test")

        await subject.set_ext("metadata", {"key": "value"})
        await subject.set_ext("tags", ["tag1", "tag2"])

        assert await subject.get_ext("metadata") == {"key": "value"}
        assert await subject.get_ext("tags") == ["tag1", "tag2"]

        # Test default=None works correctly
        value = await subject.get_ext("missing", default=None)
        assert value is None

        ext_props = await subject.get_ext_props()
        assert "metadata" in ext_props
        assert "tags" in ext_props

    async def test_subject_keys(self):
        """Subject should return list of property names via keys()"""
        subject = container.subject("test")

        await subject.set("prop1", "value1")
        await subject.set("prop2", "value2")
        await subject.set("prop3", "value3")

        keys = await subject.keys()
        assert len(keys) == 3
        assert "prop1" in keys
        assert "prop2" in keys
        assert "prop3" in keys

    async def test_subject_has(self):
        """Subject should support has() for membership testing"""
        subject = container.subject("test")

        await subject.set("exists", True)

        assert await subject.has("exists") is True
        assert await subject.has("missing") is False

    async def test_subject_dict_export(self):
        """Subject.dict() should export all properties"""
        subject = container.subject("device-123")

        await subject.set("temperature", 75)
        await subject.set("status", "ok")
        await subject.set_ext("metadata", {"location": "room1"})

        data = await subject.dict()

        assert data["name"] == "device-123"
        assert data["temperature"] == 75
        assert data["status"] == "ok"
        assert data["ext"]["metadata"] == {"location": "room1"}

    async def test_subject_muted_properties(self):
        """Muted properties should not emit change events"""
        subject = container.subject("test")

        # Normal set emits event
        await subject.set("normal", "value")

        # Muted set does not emit event
        await subject.set("muted", "value", muted=True)

        # Both should be stored
        assert await subject.get("normal") == "value"
        assert await subject.get("muted") == "value"

    async def test_subject_delete(self):
        """Subject should support property deletion"""
        subject = container.subject("test")

        await subject.set("temp", 75)
        assert await subject.has("temp") is True

        await subject.delete("temp")
        assert await subject.has("temp") is False

        with pytest.raises(AttributeError):
            await subject.get("temp")

    async def test_subject_delete_ext(self):
        """Subject should support extended property deletion"""
        subject = container.subject("test")

        await subject.set_ext("temp", "value")
        assert await subject.has_ext("temp") is True

        await subject.delete_ext("temp")
        assert await subject.has_ext("temp") is False

        with pytest.raises(AttributeError):
            await subject.get_ext("temp")

    async def test_subject_cache_transparency(self):
        """Cache should be auto-loaded transparently"""
        subject = container.subject("test")

        # First access should auto-load cache
        await subject.set("name", "John")

        # Subsequent access uses cache
        name = await subject.get("name")
        assert name == "John"

        # has() should also work without explicit load
        assert await subject.has("name") is True

    async def test_subject_set_returns_old_value(self):
        """Subject.set() should return (new_value, old_value)"""
        subject = container.subject("test")

        new_val, old_val = await subject.set("count", 10)
        assert new_val == 10
        assert old_val is None  # First set

        new_val, old_val = await subject.set("count", 20)
        assert new_val == 20
        assert old_val == 10  # Previous value

    async def test_subject_callable_with_no_args(self):
        """Subject.set() should support callable with no args"""
        subject = container.subject("test")

        # Lambda with no args
        await subject.set("random", lambda: 42)
        assert await subject.get("random") == 42

    async def test_subject_callable_with_old_value(self):
        """Subject.set() should support callable with old value arg"""
        subject = container.subject("test")

        await subject.set("count", 5)

        # Lambda with old value arg
        await subject.set("count", lambda c: c * 2)
        assert await subject.get("count") == 10

    async def test_subject_empty_keys(self):
        """Subject.keys() should return empty list for new subject"""
        subject = container.subject("empty")

        keys = await subject.keys()
        assert keys == []

    async def test_subject_string_representation(self):
        """Subject should have proper string representation (sync)"""
        subject = container.subject("test-123")

        assert str(subject) == "test-123"
        assert repr(subject) == "Subject<test-123>"

    async def test_subject_set_with_extra(self):
        """Subject.set() should pass extra dict to event handlers"""
        on, when, middleware, emit = container.handlers()

        received_extra = []

        @on("subject-property-changed")
        async def capture_extra(ctx):
            received_extra.append(ctx.extra)

        subject = container.subject("test")

        # Set without extra
        await subject.set("prop1", "value1")
        assert received_extra[-1] is None

        # Set with extra
        await subject.set("prop2", "value2", extra={"reason": "user_action", "user_id": 123})
        assert received_extra[-1] == {"reason": "user_action", "user_id": 123}

        # Set with empty extra
        await subject.set("prop3", "value3", extra={})
        assert received_extra[-1] == {}

    async def test_subject_delete_with_extra(self):
        """Subject.delete() should pass extra dict to event handlers"""
        on, when, middleware, emit = container.handlers()

        received_extra = []

        @on("subject-property-deleted")
        async def capture_extra(ctx):
            received_extra.append(ctx.extra)

        subject = container.subject("test")

        # Create properties first
        await subject.set("prop1", "value1", muted=True)
        await subject.set("prop2", "value2", muted=True)
        await subject.set("prop3", "value3", muted=True)

        # Delete without extra
        await subject.delete("prop1")
        assert received_extra[-1] is None

        # Delete with extra
        await subject.delete("prop2", extra={"reason": "expired", "timestamp": 1234567890})
        assert received_extra[-1] == {"reason": "expired", "timestamp": 1234567890}

        # Delete with empty extra
        await subject.delete("prop3", extra={})
        assert received_extra[-1] == {}

    async def test_subject_use_cache_false_set(self):
        """Subject.set() with use_cache=False should write directly to storage"""
        subject = container.subject("test")

        # Set with use_cache=False writes directly to storage
        await subject.set("prop1", "value1", use_cache=False)

        # Verify cache was not created
        assert subject._cached is None

        # Can still read value (loads from storage)
        assert await subject.get("prop1") == "value1"

    async def test_subject_use_cache_false_get(self):
        """Subject.get() with use_cache=False should read directly from storage"""
        subject1 = container.subject("test")
        subject2 = container.subject("test")

        # subject1: Set value normally (creates cache)
        await subject1.set("prop1", "value1")

        # subject2: Modify storage directly (no cache on subject2)
        await subject2.set("prop1", "value2", use_cache=False)

        # subject1: Reading with use_cache=True returns old cached value
        assert await subject1.get("prop1", use_cache=True) == "value1"

        # subject1: Reading with use_cache=False returns fresh storage value
        assert await subject1.get("prop1", use_cache=False) == "value2"

    async def test_subject_use_cache_false_delete(self):
        """Subject.delete() with use_cache=False should delete directly from storage"""
        subject = container.subject("test")

        # Create property
        await subject.set("prop1", "value1", use_cache=False)

        # Delete with use_cache=False
        await subject.delete("prop1", use_cache=False)

        # Verify it's deleted from storage
        with pytest.raises(AttributeError):
            await subject.get("prop1", use_cache=False)

    async def test_subject_use_cache_default_false(self):
        """Subject with use_cache_default=False should write directly to storage by default"""
        from krules_core.subject.storaged_subject import Subject

        # Create subject with use_cache_default=False
        subject = Subject(
            name="test-default-false",
            storage=create_test_storage(),
            event_bus=container.event_bus(),
            use_cache_default=False
        )

        # Set without explicit use_cache (should use default=False)
        await subject.set("prop1", "value1")

        # Verify cache was not created
        assert subject._cached is None

        # Can still read value
        assert await subject.get("prop1") == "value1"

    async def test_subject_use_cache_false_set_ext(self):
        """Subject.set_ext() with use_cache=False should write directly to storage"""
        subject = container.subject("test")

        # Set extended property with use_cache=False
        await subject.set_ext("ext_prop", "ext_value", use_cache=False)

        # Verify cache was not created
        assert subject._cached is None

        # Can still read value
        assert await subject.get_ext("ext_prop") == "ext_value"

    async def test_subject_use_cache_false_get_ext(self):
        """Subject.get_ext() with use_cache=False should read directly from storage"""
        subject1 = container.subject("test")
        subject2 = container.subject("test")

        # subject1: Set extended property normally (creates cache)
        await subject1.set_ext("ext_prop", "value1")

        # subject2: Modify storage directly (no cache on subject2)
        await subject2.set_ext("ext_prop", "value2", use_cache=False)

        # subject1: Reading with use_cache=True returns old cached value
        assert await subject1.get_ext("ext_prop", use_cache=True) == "value1"

        # subject1: Reading with use_cache=False returns fresh storage value
        assert await subject1.get_ext("ext_prop", use_cache=False) == "value2"

    async def test_subject_use_cache_false_delete_ext(self):
        """Subject.delete_ext() with use_cache=False should delete directly from storage"""
        subject = container.subject("test")

        # Create extended property
        await subject.set_ext("ext_prop", "value1", use_cache=False)

        # Delete with use_cache=False
        await subject.delete_ext("ext_prop", use_cache=False)

        # Verify it's deleted from storage
        with pytest.raises(AttributeError):
            await subject.get_ext("ext_prop", use_cache=False)

    async def test_subject_use_cache_false_callable(self):
        """Subject.set() with use_cache=False should handle callables atomically"""
        subject = container.subject("counter")

        # Initialize counter
        await subject.set("count", 0, use_cache=False)

        # Increment with callable and use_cache=False (atomic operation in storage)
        await subject.set("count", lambda c: c + 1, use_cache=False)
        await subject.set("count", lambda c: c + 1, use_cache=False)
        await subject.set("count", lambda c: c + 1, use_cache=False)

        # Verify final value
        assert await subject.get("count", use_cache=False) == 3

    async def test_subject_use_cache_sync_after_direct_write(self):
        """Cache should sync with storage after direct write when cache exists"""
        from krules_core.subject import PropertyType

        subject = container.subject("test")

        # Create cache by reading
        await subject.set("prop1", "value1")
        assert subject._cached is not None

        # Write directly to storage with use_cache=False
        await subject.set("prop1", "value2", use_cache=False)

        # Cache should be updated
        assert subject._cached[PropertyType.DEFAULT]["values"]["prop1"] == "value2"
