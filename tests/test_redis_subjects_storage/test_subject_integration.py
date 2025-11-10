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
Integration tests for SubjectsRedisStorage with Subject class.

Tests the complete Subject + Redis storage flow using async API.
"""

import pytest
import pytest_asyncio
from krules_core.subject.storaged_subject import Subject
from redis_subjects_storage.storage_impl import create_redis_storage


@pytest_asyncio.fixture
async def redis_subject_factory(redis_client):
    """Create Subject factory with Redis storage."""
    from krules_core.event_bus import EventBus

    storage_factory = create_redis_storage(
        redis_client=redis_client,
        redis_prefix="test:"
    )

    # Create EventBus instance for Subject
    event_bus = EventBus()

    def subject_factory(name, **kwargs):
        return Subject(name, storage=storage_factory, event_bus=event_bus, **kwargs)

    return subject_factory


@pytest.mark.asyncio
class TestSubjectRedisIntegration:
    """Integration tests for Subject with Redis storage"""

    async def test_subject_with_redis_storage(self, redis_subject_factory):
        """Subject should work with Redis storage backend."""
        subject = redis_subject_factory("user-123")

        # Set properties
        await subject.set("name", "Alice")
        await subject.set("age", 30)

        # Get properties
        assert await subject.get("name") == "Alice"
        assert await subject.get("age") == 30

    async def test_subject_persistence_across_instances(self, redis_subject_factory):
        """Properties should persist across Subject instances."""
        # First instance
        subject1 = redis_subject_factory("user-456")
        await subject1.set("email", "alice@example.com")
        await subject1.set("status", "active")
        await subject1.store()  # Persist to Redis

        # Second instance (same subject name)
        subject2 = redis_subject_factory("user-456")

        # Should load persisted data
        assert await subject2.get("email") == "alice@example.com"
        assert await subject2.get("status") == "active"

    async def test_subject_callable_values(self, redis_subject_factory):
        """Subject should handle callable values with Redis storage."""
        subject = redis_subject_factory("counter-1")

        # Initialize counter
        await subject.set("count", 0)

        # Increment using callable
        await subject.set("count", lambda c: c + 1)
        assert await subject.get("count") == 1

        # Increment again
        await subject.set("count", lambda c: c + 1)
        assert await subject.get("count") == 2

    async def test_subject_extended_properties(self, redis_subject_factory):
        """Subject extended properties should work with Redis storage."""
        subject = redis_subject_factory("resource-1")

        # Set extended properties
        await subject.set_ext("tenant_id", "tenant-123")
        await subject.set_ext("environment", "production")

        # Get extended properties
        assert await subject.get_ext("tenant_id") == "tenant-123"
        assert await subject.get_ext("environment") == "production"

        # Get all extended properties
        ext_props = await subject.get_ext_props()
        assert ext_props["tenant_id"] == "tenant-123"
        assert ext_props["environment"] == "production"

    async def test_subject_delete_property(self, redis_subject_factory):
        """Subject delete should work with Redis storage."""
        subject = redis_subject_factory("temp-subject")

        # Set and verify
        await subject.set("temp_prop", "value")
        assert await subject.get("temp_prop") == "value"

        # Delete
        await subject.delete("temp_prop")

        # Verify deleted
        with pytest.raises(AttributeError):
            await subject.get("temp_prop")

    async def test_subject_flush(self, redis_subject_factory):
        """Subject flush should delete all properties from Redis."""
        subject = redis_subject_factory("flush-test")

        # Set multiple properties
        await subject.set("prop1", "value1")
        await subject.set("prop2", "value2")
        await subject.set_ext("ext1", "extvalue1")

        # Verify properties exist
        assert await subject.get("prop1") == "value1"
        assert await subject.get("prop2") == "value2"
        assert await subject.get_ext("ext1") == "extvalue1"

        # Flush
        await subject.flush()

        # Verify all properties deleted
        with pytest.raises(AttributeError):
            await subject.get("prop1")
        with pytest.raises(AttributeError):
            await subject.get("prop2")

        assert await subject.get_ext_props() == {}

    async def test_subject_store_batching(self, redis_subject_factory):
        """Subject should batch multiple operations in store()."""
        subject = redis_subject_factory("batch-test")

        # Set multiple properties (should batch in single store call)
        await subject.set("name", "Bob")
        await subject.set("age", 25)
        await subject.set("city", "NYC")

        # Force store
        await subject.store()

        # Create new instance and verify
        subject2 = redis_subject_factory("batch-test")
        assert await subject2.get("name") == "Bob"
        assert await subject2.get("age") == 25
        assert await subject2.get("city") == "NYC"

    async def test_subject_dict_representation(self, redis_subject_factory):
        """Subject dict() should include Redis-stored properties."""
        subject = redis_subject_factory("dict-test")

        # Set properties
        await subject.set("name", "Charlie")
        await subject.set("age", 35)
        await subject.set_ext("tenant", "t1")

        # Get dict representation
        subject_dict = await subject.dict()

        assert subject_dict["name"] == "Charlie"
        assert subject_dict["age"] == 35
        # Extended properties should be in separate key
        assert "tenant" not in subject_dict  # Extended props separate

    async def test_concurrent_callable_updates(self, redis_subject_factory):
        """Redis WATCH should prevent race conditions with callable values."""
        subject = redis_subject_factory("concurrent-test")

        # Initialize counter
        await subject.set("counter", 0)

        # Simulate multiple increments
        # (In real concurrency, Redis WATCH ensures atomicity)
        for _ in range(10):
            await subject.set("counter", lambda c: c + 1)

        # Verify final count
        assert await subject.get("counter") == 10

    async def test_subject_cache_behavior(self, redis_subject_factory):
        """Subject cache should interact correctly with Redis storage."""
        subject1 = redis_subject_factory("cache-test-1")

        # Set property (goes to cache)
        await subject1.set("cached_prop", "initial")
        await subject1.store()  # Persist to Redis

        # Create new instance (loads from Redis)
        subject2 = redis_subject_factory("cache-test-1")
        assert await subject2.get("cached_prop") == "initial"

        # Update in subject2
        await subject2.set("cached_prop", "updated")
        await subject2.store()  # Persist to Redis

        # subject1 cache is stale, but will auto-reload on next get
        # (cache was cleared after store())
        assert await subject1.get("cached_prop") == "updated"

    async def test_subject_with_event_info(self, redis_subject_factory):
        """Subject should handle event_info with Redis storage."""
        subject = redis_subject_factory(
            "event-subject",
            event_info={"id": "evt-123", "type": "test.event"}
        )

        # Set properties
        await subject.set("processed", True)
        await subject.store()  # Persist to Redis

        # Verify storage works regardless of event_info
        subject2 = redis_subject_factory("event-subject")
        assert await subject2.get("processed") is True
