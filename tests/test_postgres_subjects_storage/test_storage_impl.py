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
Tests for SubjectsPostgresStorage implementation.
"""

import json
import pytest
import asyncio
from postgres_subjects_storage.storage_impl import SubjectsPostgresStorage, create_postgres_storage
from krules_core.subject import PropertyType


class Property:
    """
    Helper class for testing storage operations.

    Mimics the Property interface expected by SubjectsPostgresStorage.
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


@pytest.mark.asyncio
class TestSubjectsPostgresStorage:
    """Test suite for SubjectsPostgresStorage"""

    async def test_storage_initialization(self, postgres_storage, subject_name):
        """Storage should initialize with correct configuration."""
        assert postgres_storage._subject == subject_name
        assert postgres_storage._pool is not None

    async def test_is_concurrency_safe(self, postgres_storage):
        """PostgreSQL storage should be concurrency safe."""
        assert postgres_storage.is_concurrency_safe() is True

    async def test_is_persistent(self, postgres_storage):
        """PostgreSQL storage should be persistent."""
        assert postgres_storage.is_persistent() is True

    async def test_load_empty_subject(self, postgres_storage):
        """Loading non-existent subject should return empty dicts."""
        default_props, ext_props = await postgres_storage.load()

        assert default_props == {}
        assert ext_props == {}

    async def test_store_inserts(self, postgres_storage):
        """Store should insert new properties."""
        # Create properties to insert
        prop1 = Property("name", "John", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        prop3 = Property("tenant_id", "abc-123", PropertyType.EXTENDED)

        # Store properties
        await postgres_storage.store(inserts=[prop1, prop2, prop3])

        # Load and verify
        default_props, ext_props = await postgres_storage.load()

        assert default_props["name"] == "John"
        assert default_props["age"] == 30
        assert ext_props["tenant_id"] == "abc-123"

    async def test_store_updates(self, postgres_storage):
        """Store should update existing properties."""
        # Insert initial properties
        prop1 = Property("count", 10, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1])

        # Update property
        prop2 = Property("count", 20, PropertyType.DEFAULT)
        await postgres_storage.store(updates=[prop2])

        # Load and verify
        default_props, _ = await postgres_storage.load()
        assert default_props["count"] == 20

    async def test_store_deletes(self, postgres_storage):
        """Store should delete properties."""
        # Insert properties
        prop1 = Property("name", "John", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1, prop2])

        # Delete one property
        prop_to_delete = Property("age", None, PropertyType.DEFAULT)
        await postgres_storage.store(deletes=[prop_to_delete])

        # Load and verify
        default_props, _ = await postgres_storage.load()
        assert "name" in default_props
        assert "age" not in default_props

    async def test_store_mixed_operations(self, postgres_storage):
        """Store should handle inserts, updates, and deletes together."""
        # Initial state
        prop1 = Property("name", "John", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        prop3 = Property("status", "active", PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1, prop2, prop3])

        # Mixed operations: update name, delete age, insert city
        update_prop = Property("name", "Jane", PropertyType.DEFAULT)
        delete_prop = Property("age", None, PropertyType.DEFAULT)
        insert_prop = Property("city", "NYC", PropertyType.DEFAULT)

        await postgres_storage.store(
            updates=[update_prop],
            deletes=[delete_prop],
            inserts=[insert_prop]
        )

        # Verify
        default_props, _ = await postgres_storage.load()
        assert default_props["name"] == "Jane"  # Updated
        assert "age" not in default_props  # Deleted
        assert default_props["city"] == "NYC"  # Inserted
        assert default_props["status"] == "active"  # Unchanged

    async def test_set_simple_value(self, postgres_storage):
        """Set should work with simple non-callable values."""
        prop = Property("name", "Alice", PropertyType.DEFAULT)

        new_value, old_value = await postgres_storage.set(prop, old_value_default=None)

        assert new_value == "Alice"
        assert old_value is None

        # Verify stored
        default_props, _ = await postgres_storage.load()
        assert default_props["name"] == "Alice"

    async def test_set_update_existing(self, postgres_storage):
        """Set should return old value when updating existing property."""
        # Insert initial value
        prop1 = Property("count", 10, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1])

        # Update via set
        prop2 = Property("count", 20, PropertyType.DEFAULT)
        new_value, old_value = await postgres_storage.set(prop2)

        assert new_value == 20
        assert old_value == 10

    async def test_set_callable_value(self, postgres_storage):
        """Set should handle callable values atomically."""
        # Insert initial counter
        prop1 = Property("counter", 0, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1])

        # Increment using callable
        prop2 = Property("counter", lambda c: c + 1, PropertyType.DEFAULT)
        new_value, old_value = await postgres_storage.set(prop2)

        assert old_value == 0
        assert new_value == 1

        # Verify stored
        default_props, _ = await postgres_storage.load()
        assert default_props["counter"] == 1

    async def test_set_callable_with_default(self, postgres_storage):
        """Set should use default value for callable on non-existent property."""
        # Counter doesn't exist yet
        prop = Property("counter", lambda c: c + 1, PropertyType.DEFAULT)
        new_value, old_value = await postgres_storage.set(prop, old_value_default=0)

        assert old_value == 0
        assert new_value == 1

    async def test_get_existing_property(self, postgres_storage):
        """Get should retrieve existing property."""
        # Insert property
        prop1 = Property("name", "Bob", PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1])

        # Get property
        prop2 = Property("name", None, PropertyType.DEFAULT)
        value = await postgres_storage.get(prop2)

        assert value == "Bob"

    async def test_get_non_existent_property(self, postgres_storage):
        """Get should raise AttributeError for non-existent property."""
        prop = Property("nonexistent", None, PropertyType.DEFAULT)

        with pytest.raises(AttributeError) as exc_info:
            await postgres_storage.get(prop)

        assert "nonexistent" in str(exc_info.value)

    async def test_get_extended_property(self, postgres_storage):
        """Get should work with extended properties."""
        # Insert extended property
        prop1 = Property("tenant_id", "tenant-123", PropertyType.EXTENDED)
        await postgres_storage.store(inserts=[prop1])

        # Get extended property
        prop2 = Property("tenant_id", None, PropertyType.EXTENDED)
        value = await postgres_storage.get(prop2)

        assert value == "tenant-123"

    async def test_delete_existing_property(self, postgres_storage):
        """Delete should remove existing property."""
        # Insert property
        prop1 = Property("temp", "value", PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1])

        # Delete property
        prop2 = Property("temp", None, PropertyType.DEFAULT)
        await postgres_storage.delete(prop2)

        # Verify deleted
        default_props, _ = await postgres_storage.load()
        assert "temp" not in default_props

    async def test_delete_non_existent_property(self, postgres_storage):
        """Delete should not raise error for non-existent property."""
        # Delete non-existent property (should not raise)
        prop = Property("nonexistent", None, PropertyType.DEFAULT)
        await postgres_storage.delete(prop)  # Should not raise

    async def test_get_ext_props(self, postgres_storage):
        """get_ext_props should return only extended properties."""
        # Insert mixed properties
        default_prop = Property("name", "Alice", PropertyType.DEFAULT)
        ext_prop1 = Property("tenant_id", "tenant-1", PropertyType.EXTENDED)
        ext_prop2 = Property("environment", "prod", PropertyType.EXTENDED)

        await postgres_storage.store(inserts=[default_prop, ext_prop1, ext_prop2])

        # Get extended properties
        ext_props = await postgres_storage.get_ext_props()

        assert len(ext_props) == 2
        assert ext_props["tenant_id"] == "tenant-1"
        assert ext_props["environment"] == "prod"
        assert "name" not in ext_props  # Default property excluded

    async def test_get_ext_props_empty(self, postgres_storage):
        """get_ext_props should return empty dict when no extended properties."""
        # Insert only default properties
        prop = Property("name", "Alice", PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop])

        ext_props = await postgres_storage.get_ext_props()

        assert ext_props == {}

    async def test_flush_deletes_all_properties(self, postgres_storage):
        """Flush should delete entire subject from PostgreSQL."""
        # Insert multiple properties
        prop1 = Property("name", "Alice", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        prop3 = Property("tenant_id", "t1", PropertyType.EXTENDED)

        await postgres_storage.store(inserts=[prop1, prop2, prop3])

        # Verify stored
        default_props, ext_props = await postgres_storage.load()
        assert len(default_props) == 2
        assert len(ext_props) == 1

        # Flush
        await postgres_storage.flush()

        # Verify deleted
        default_props, ext_props = await postgres_storage.load()
        assert default_props == {}
        assert ext_props == {}

    async def test_subject_isolation(self, postgres_storage_factory):
        """Different subjects should be isolated."""
        # Create storages for different subjects
        storage1 = postgres_storage_factory("subject-1")
        storage2 = postgres_storage_factory("subject-2")

        # Store in storage1
        prop1 = Property("name", "Subject1", PropertyType.DEFAULT)
        await storage1.store(inserts=[prop1])

        # Load from storage2 (different subject)
        default_props, _ = await storage2.load()
        assert default_props == {}  # Should be empty

        # Store in storage2
        prop2 = Property("name", "Subject2", PropertyType.DEFAULT)
        await storage2.store(inserts=[prop2])

        # Verify isolation
        props1, _ = await storage1.load()
        props2, _ = await storage2.load()

        assert props1["name"] == "Subject1"
        assert props2["name"] == "Subject2"


@pytest.mark.asyncio
class TestConcurrentOperations:
    """Test suite for concurrent operations and atomicity"""

    async def test_concurrent_callable_increments(self, postgres_storage):
        """Concurrent callable increments should be atomic (no lost updates)."""
        # Initialize counter
        prop = Property("counter", 0, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop])

        # Spawn 50 concurrent increments
        async def increment():
            prop = Property("counter", lambda c: c + 1, PropertyType.DEFAULT)
            await postgres_storage.set(prop)

        tasks = [increment() for _ in range(50)]
        await asyncio.gather(*tasks)

        # Verify: should be exactly 50 (no lost updates)
        default_props, _ = await postgres_storage.load()
        assert default_props["counter"] == 50

    async def test_concurrent_updates_different_properties(self, postgres_storage):
        """Concurrent updates to different properties should work correctly."""
        # Initialize properties
        prop1 = Property("count1", 0, PropertyType.DEFAULT)
        prop2 = Property("count2", 0, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1, prop2])

        # Concurrent increments on different properties
        async def increment_count1():
            for _ in range(10):
                prop = Property("count1", lambda c: c + 1, PropertyType.DEFAULT)
                await postgres_storage.set(prop)

        async def increment_count2():
            for _ in range(10):
                prop = Property("count2", lambda c: c + 1, PropertyType.DEFAULT)
                await postgres_storage.set(prop)

        await asyncio.gather(increment_count1(), increment_count2())

        # Verify both counters
        default_props, _ = await postgres_storage.load()
        assert default_props["count1"] == 10
        assert default_props["count2"] == 10

    async def test_concurrent_mixed_operations(self, postgres_storage):
        """Mixed concurrent operations (read, write, delete) should be safe."""
        # Initialize data
        prop1 = Property("name", "Alice", PropertyType.DEFAULT)
        prop2 = Property("age", 30, PropertyType.DEFAULT)
        await postgres_storage.store(inserts=[prop1, prop2])

        async def reader():
            """Read operations"""
            for _ in range(5):
                await postgres_storage.load()
                await asyncio.sleep(0.001)

        async def writer():
            """Write operations"""
            for i in range(5):
                prop = Property("name", f"Alice-{i}", PropertyType.DEFAULT)
                await postgres_storage.store(updates=[prop])
                await asyncio.sleep(0.001)

        async def incrementer():
            """Callable operations"""
            for _ in range(5):
                prop = Property("age", lambda a: a + 1, PropertyType.DEFAULT)
                await postgres_storage.set(prop)
                await asyncio.sleep(0.001)

        # Run concurrently
        await asyncio.gather(reader(), writer(), incrementer())

        # Verify final state (no crashes, data consistent)
        default_props, _ = await postgres_storage.load()
        assert "name" in default_props
        assert default_props["age"] == 35  # 30 + 5 increments


@pytest.mark.asyncio
class TestCreatePostgresStorage:
    """Test suite for create_postgres_storage factory"""

    async def test_factory_creates_storage_instance(self, postgres_pool):
        """Factory should create SubjectsPostgresStorage instances."""
        factory = create_postgres_storage(pool=postgres_pool)

        storage = factory("subject-123")

        assert isinstance(storage, SubjectsPostgresStorage)
        assert storage._subject == "subject-123"
        assert storage._pool == postgres_pool

    async def test_factory_ignores_extra_kwargs(self, postgres_pool):
        """Factory should accept but ignore event_info and event_data kwargs."""
        factory = create_postgres_storage(pool=postgres_pool)

        # Should not raise even with extra kwargs
        storage = factory(
            "subject-456",
            event_info={"id": "evt-1"},
            event_data={"payload": "data"}
        )

        assert isinstance(storage, SubjectsPostgresStorage)
        assert storage._subject == "subject-456"
