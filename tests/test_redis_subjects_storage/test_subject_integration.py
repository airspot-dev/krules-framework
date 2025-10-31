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

Tests the complete Subject + Redis storage flow.
"""

import pytest
from krules_core.subject.storaged_subject import Subject
from redis_subjects_storage.storage_impl import create_redis_storage


@pytest.fixture
def redis_subject_factory(redis_url):
    """Create Subject factory with Redis storage."""
    from krules_core.event_bus import EventBus

    storage_factory = create_redis_storage(
        redis_url=redis_url,
        redis_prefix="test:"
    )

    # Create EventBus instance for Subject
    event_bus = EventBus()

    def subject_factory(name, **kwargs):
        return Subject(name, storage=storage_factory, event_bus=event_bus, **kwargs)

    return subject_factory


class TestSubjectRedisIntegration:
    """Integration tests for Subject with Redis storage"""

    def test_subject_with_redis_storage(self, redis_subject_factory):
        """Subject should work with Redis storage backend."""
        subject = redis_subject_factory("user-123")

        # Set properties
        subject.set("name", "Alice")
        subject.set("age", 30)

        # Get properties
        assert subject.get("name") == "Alice"
        assert subject.get("age") == 30

    def test_subject_persistence_across_instances(self, redis_subject_factory):
        """Properties should persist across Subject instances."""
        # First instance
        subject1 = redis_subject_factory("user-456")
        subject1.set("email", "alice@example.com")
        subject1.set("status", "active")
        subject1.store()  # Persist to Redis

        # Second instance (same subject name)
        subject2 = redis_subject_factory("user-456")

        # Should load persisted data
        assert subject2.get("email") == "alice@example.com"
        assert subject2.get("status") == "active"

    def test_subject_callable_values(self, redis_subject_factory):
        """Subject should handle callable values with Redis storage."""
        subject = redis_subject_factory("counter-1")

        # Initialize counter
        subject.set("count", 0)

        # Increment using callable
        subject.set("count", lambda c: c + 1)
        assert subject.get("count") == 1

        # Increment again
        subject.set("count", lambda c: c + 1)
        assert subject.get("count") == 2

    def test_subject_extended_properties(self, redis_subject_factory):
        """Subject extended properties should work with Redis storage."""
        subject = redis_subject_factory("resource-1")

        # Set extended properties
        subject.set_ext("tenant_id", "tenant-123")
        subject.set_ext("environment", "production")

        # Get extended properties
        assert subject.get_ext("tenant_id") == "tenant-123"
        assert subject.get_ext("environment") == "production"

        # Get all extended properties
        ext_props = subject.get_ext_props()
        assert ext_props["tenant_id"] == "tenant-123"
        assert ext_props["environment"] == "production"

    def test_subject_delete_property(self, redis_subject_factory):
        """Subject delete should work with Redis storage."""
        subject = redis_subject_factory("temp-subject")

        # Set and verify
        subject.set("temp_prop", "value")
        assert subject.get("temp_prop") == "value"

        # Delete
        subject.delete("temp_prop")

        # Verify deleted
        with pytest.raises(AttributeError):
            subject.get("temp_prop")

    def test_subject_flush(self, redis_subject_factory):
        """Subject flush should delete all properties from Redis."""
        subject = redis_subject_factory("flush-test")

        # Set multiple properties
        subject.set("prop1", "value1")
        subject.set("prop2", "value2")
        subject.set_ext("ext1", "extvalue1")

        # Verify properties exist
        assert subject.get("prop1") == "value1"
        assert subject.get("prop2") == "value2"
        assert subject.get_ext("ext1") == "extvalue1"

        # Flush
        subject.flush()

        # Verify all properties deleted
        with pytest.raises(AttributeError):
            subject.get("prop1")
        with pytest.raises(AttributeError):
            subject.get("prop2")

        assert subject.get_ext_props() == {}

    def test_subject_store_batching(self, redis_subject_factory):
        """Subject should batch multiple operations in store()."""
        subject = redis_subject_factory("batch-test")

        # Set multiple properties (should batch in single store call)
        subject.set("name", "Bob")
        subject.set("age", 25)
        subject.set("city", "NYC")

        # Force store
        subject.store()

        # Create new instance and verify
        subject2 = redis_subject_factory("batch-test")
        assert subject2.get("name") == "Bob"
        assert subject2.get("age") == 25
        assert subject2.get("city") == "NYC"

    def test_subject_dict_representation(self, redis_subject_factory):
        """Subject dict() should include Redis-stored properties."""
        subject = redis_subject_factory("dict-test")

        # Set properties
        subject.set("name", "Charlie")
        subject.set("age", 35)
        subject.set_ext("tenant", "t1")

        # Get dict representation
        subject_dict = subject.dict()

        assert subject_dict["name"] == "Charlie"
        assert subject_dict["age"] == 35
        # Extended properties should be in separate key
        assert "tenant" not in subject_dict  # Extended props separate

    def test_concurrent_callable_updates(self, redis_subject_factory):
        """Redis WATCH should prevent race conditions with callable values."""
        subject = redis_subject_factory("concurrent-test")

        # Initialize counter
        subject.set("counter", 0)

        # Simulate multiple increments
        # (In real concurrency, Redis WATCH ensures atomicity)
        for _ in range(10):
            subject.set("counter", lambda c: c + 1)

        # Verify final count
        assert subject.get("counter") == 10

    def test_subject_cache_behavior(self, redis_subject_factory):
        """Subject cache should interact correctly with Redis storage."""
        subject1 = redis_subject_factory("cache-test-1")

        # Set property (goes to cache)
        subject1.set("cached_prop", "initial")
        subject1.store()  # Persist to Redis

        # Create new instance (loads from Redis)
        subject2 = redis_subject_factory("cache-test-1")
        assert subject2.get("cached_prop") == "initial"

        # Update in subject2
        subject2.set("cached_prop", "updated")
        subject2.store()  # Persist to Redis

        # Verify use_cache=False bypasses cache and reads from storage
        assert subject1.get("cached_prop", use_cache=False) == "updated"

        # Now subject1's cache is updated (get with use_cache=False updates cache)
        assert subject1.get("cached_prop", use_cache=True) == "updated"

    def test_subject_with_event_info(self, redis_subject_factory):
        """Subject should handle event_info with Redis storage."""
        subject = redis_subject_factory(
            "event-subject",
            event_info={"id": "evt-123", "type": "test.event"}
        )

        # Set properties
        subject.set("processed", True)
        subject.store()  # Persist to Redis

        # Verify storage works regardless of event_info
        subject2 = redis_subject_factory("event-subject")
        assert subject2.get("processed") is True
