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
Tests for SubjectsRedisStorage implementation.
"""

import json
import pytest
from redis_subjects_storage.storage_impl import SubjectsRedisStorage, create_redis_storage
from krules_core.subject import PropertyType


class Property:
    """
    Helper class for testing storage operations.

    Mimics the Property interface expected by SubjectsRedisStorage.
    """
    def __init__(self, name: str, value, prop_type: str = PropertyType.DEFAULT):
        self.name = name
        self.value = value
        self.type = prop_type

    def json_value(self, old_value=None):
        """Return JSON-serialized value."""
        if callable(self.value):
            # For callable values, call the function and serialize result
            result = self.value(old_value)
            return json.dumps(result)
        return json.dumps(self.value)

    def get_value(self):
        """Return the value (for non-callable values)."""
        return self.value


class TestSubjectsRedisStorage:
    """Test suite for SubjectsRedisStorage"""

    def test_storage_initialization(self, redis_storage, subject_name):
        """Storage should initialize with correct configuration."""
        assert redis_storage._subject == subject_name
        assert redis_storage._key_prefix == "test:"
        assert redis_storage._conn is not None

    def test_is_concurrency_safe(self, redis_storage):
        """Redis storage should be concurrency safe."""
        assert redis_storage.is_concurrency_safe() is True

    def test_is_persistent(self, redis_storage):
        """Redis storage should be persistent."""
        assert redis_storage.is_persistent() is True

    def test_load_empty_subject(self, redis_storage):
        """Loading non-existent subject should return empty dicts."""
        default_props, ext_props = redis_storage.load()

        assert default_props == {}
        assert ext_props == {}

    def test_store_inserts(self, redis_storage):
        """Store should insert new properties."""
        # Create properties to insert
        prop1 = Property("name", "John", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        prop3 = Property("tenant_id", "abc-123", PropertyType.EXTENDED)

        # Store properties
        redis_storage.store(inserts=[prop1, prop2, prop3])

        # Load and verify
        default_props, ext_props = redis_storage.load()

        assert default_props["name"] == "John"
        assert default_props["age"] == 30
        assert ext_props["tenant_id"] == "abc-123"

    def test_store_updates(self, redis_storage):
        """Store should update existing properties."""
        # Insert initial properties
        prop1 = Property("count", 10, PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1])

        # Update property
        prop2 = Property("count", 20, PropertyType.DEFAULT)
        redis_storage.store(updates=[prop2])

        # Load and verify
        default_props, _ = redis_storage.load()
        assert default_props["count"] == 20

    def test_store_deletes(self, redis_storage):
        """Store should delete properties."""
        # Insert properties
        prop1 = Property("name", "John", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1, prop2])

        # Delete one property
        prop_to_delete = Property("age", None, PropertyType.DEFAULT)
        redis_storage.store(deletes=[prop_to_delete])

        # Load and verify
        default_props, _ = redis_storage.load()
        assert "name" in default_props
        assert "age" not in default_props

    def test_store_mixed_operations(self, redis_storage):
        """Store should handle inserts, updates, and deletes together."""
        # Initial state
        prop1 = Property("name", "John", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        prop3 = Property("status", "active", PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1, prop2, prop3])

        # Mixed operations: update name, delete age, insert city
        update_prop = Property("name", "Jane", PropertyType.DEFAULT)
        delete_prop = Property("age", None, PropertyType.DEFAULT)
        insert_prop = Property("city", "NYC", PropertyType.DEFAULT)

        redis_storage.store(
            updates=[update_prop],
            deletes=[delete_prop],
            inserts=[insert_prop]
        )

        # Verify
        default_props, _ = redis_storage.load()
        assert default_props["name"] == "Jane"  # Updated
        assert "age" not in default_props  # Deleted
        assert default_props["city"] == "NYC"  # Inserted
        assert default_props["status"] == "active"  # Unchanged

    def test_set_simple_value(self, redis_storage):
        """Set should work with simple non-callable values."""
        prop = Property("name", "Alice", PropertyType.DEFAULT)

        new_value, old_value = redis_storage.set(prop, old_value_default=None)

        assert new_value == "Alice"
        assert old_value is None

        # Verify stored
        default_props, _ = redis_storage.load()
        assert default_props["name"] == "Alice"

    def test_set_update_existing(self, redis_storage):
        """Set should return old value when updating existing property."""
        # Insert initial value
        prop1 = Property("count", 10, PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1])

        # Update via set
        prop2 = Property("count", 20, PropertyType.DEFAULT)
        new_value, old_value = redis_storage.set(prop2)

        assert new_value == 20
        assert old_value == 10

    def test_set_callable_value(self, redis_storage):
        """Set should handle callable values atomically."""
        # Insert initial counter
        prop1 = Property("counter", 0, PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1])

        # Increment using callable
        prop2 = Property("counter", lambda c: c + 1, PropertyType.DEFAULT)
        new_value, old_value = redis_storage.set(prop2)

        assert old_value == 0
        assert new_value == 1

        # Verify stored
        default_props, _ = redis_storage.load()
        assert default_props["counter"] == 1

    def test_set_callable_with_default(self, redis_storage):
        """Set should use default value for callable on non-existent property."""
        # Counter doesn't exist yet
        prop = Property("counter", lambda c: c + 1, PropertyType.DEFAULT)
        new_value, old_value = redis_storage.set(prop, old_value_default=0)

        assert old_value == 0
        assert new_value == 1

    def test_get_existing_property(self, redis_storage):
        """Get should retrieve existing property."""
        # Insert property
        prop1 = Property("name", "Bob", PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1])

        # Get property
        prop2 = Property("name", None, PropertyType.DEFAULT)
        value = redis_storage.get(prop2)

        assert value == "Bob"

    def test_get_non_existent_property(self, redis_storage):
        """Get should raise AttributeError for non-existent property."""
        prop = Property("nonexistent", None, PropertyType.DEFAULT)

        with pytest.raises(AttributeError) as exc_info:
            redis_storage.get(prop)

        assert "nonexistent" in str(exc_info.value)

    def test_get_extended_property(self, redis_storage):
        """Get should work with extended properties."""
        # Insert extended property
        prop1 = Property("tenant_id", "tenant-123", PropertyType.EXTENDED)
        redis_storage.store(inserts=[prop1])

        # Get extended property
        prop2 = Property("tenant_id", None, PropertyType.EXTENDED)
        value = redis_storage.get(prop2)

        assert value == "tenant-123"

    def test_delete_existing_property(self, redis_storage):
        """Delete should remove existing property."""
        # Insert property
        prop1 = Property("temp", "value", PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop1])

        # Delete property
        prop2 = Property("temp", None, PropertyType.DEFAULT)
        redis_storage.delete(prop2)

        # Verify deleted
        default_props, _ = redis_storage.load()
        assert "temp" not in default_props

    def test_delete_non_existent_property(self, redis_storage):
        """Delete should not raise error for non-existent property."""
        # Delete non-existent property (should not raise)
        prop = Property("nonexistent", None, PropertyType.DEFAULT)
        redis_storage.delete(prop)  # Should not raise

    def test_get_ext_props(self, redis_storage):
        """get_ext_props should return only extended properties."""
        # Insert mixed properties
        default_prop = Property("name", "Alice", PropertyType.DEFAULT)
        ext_prop1 = Property("tenant_id", "tenant-1", PropertyType.EXTENDED)
        ext_prop2 = Property("environment", "prod", PropertyType.EXTENDED)

        redis_storage.store(inserts=[default_prop, ext_prop1, ext_prop2])

        # Get extended properties
        ext_props = redis_storage.get_ext_props()

        assert len(ext_props) == 2
        assert ext_props["tenant_id"] == "tenant-1"
        assert ext_props["environment"] == "prod"
        assert "name" not in ext_props  # Default property excluded

    def test_get_ext_props_empty(self, redis_storage):
        """get_ext_props should return empty dict when no extended properties."""
        # Insert only default properties
        prop = Property("name", "Alice", PropertyType.DEFAULT)
        redis_storage.store(inserts=[prop])

        ext_props = redis_storage.get_ext_props()

        assert ext_props == {}

    def test_flush_deletes_all_properties(self, redis_storage):
        """Flush should delete entire subject from Redis."""
        # Insert multiple properties
        prop1 = Property("name", "Alice", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        prop3 = Property("tenant_id", "t1", PropertyType.EXTENDED)

        redis_storage.store(inserts=[prop1, prop2, prop3])

        # Verify stored
        default_props, ext_props = redis_storage.load()
        assert len(default_props) == 2
        assert len(ext_props) == 1

        # Flush
        redis_storage.flush()

        # Verify deleted
        default_props, ext_props = redis_storage.load()
        assert default_props == {}
        assert ext_props == {}

    def test_key_prefix_isolation(self, redis_storage_factory, redis_connection):
        """Different key prefixes should isolate subjects."""
        # Create storage with different prefix
        storage1 = redis_storage_factory("shared-name")

        from redis_subjects_storage.storage_impl import SubjectsRedisStorage
        storage2 = SubjectsRedisStorage(
            subject="shared-name",
            url="redis://localhost:6379/0",
            key_prefix="other:"
        )

        # Store in storage1
        prop1 = Property("name", "Storage1", PropertyType.DEFAULT)
        storage1.store(inserts=[prop1])

        # Load from storage2 (different prefix)
        default_props, _ = storage2.load()
        assert default_props == {}  # Should be empty

        # Store in storage2
        prop2 = Property("name", "Storage2", PropertyType.DEFAULT)
        storage2.store(inserts=[prop2])

        # Verify isolation
        props1, _ = storage1.load()
        props2, _ = storage2.load()

        assert props1["name"] == "Storage1"
        assert props2["name"] == "Storage2"
        # Cleanup is handled by autouse fixture


class TestCreateRedisStorage:
    """Test suite for create_redis_storage factory"""

    def test_factory_creates_storage_instance(self):
        """Factory should create SubjectsRedisStorage instances."""
        factory = create_redis_storage(
            redis_url="redis://localhost:6379/0",
            redis_prefix="test:"
        )

        storage = factory("subject-123")

        assert isinstance(storage, SubjectsRedisStorage)
        assert storage._subject == "subject-123"
        assert storage._key_prefix == "test:"

    def test_factory_ignores_extra_kwargs(self):
        """Factory should accept but ignore event_info and event_data kwargs."""
        factory = create_redis_storage(
            redis_url="redis://localhost:6379/0",
            redis_prefix="test:"
        )

        # Should not raise even with extra kwargs
        storage = factory(
            "subject-456",
            event_info={"id": "evt-1"},
            event_data={"payload": "data"}
        )

        assert isinstance(storage, SubjectsRedisStorage)
        assert storage._subject == "subject-456"
