"""
In-memory storage for testing use_cache functionality.

Unlike EmptySubjectStorage, this actually stores data.
"""

from krules_core.subject import PropertyType, SubjectProperty, SubjectExtProperty
import inspect


class InMemoryTestStorage:
    """
    Simple in-memory storage for testing.

    Unlike EmptySubjectStorage, this actually persists data in a dict.
    """

    # Class-level storage (shared across all instances)
    _storage = {}

    def __init__(self, subject_name):
        self._subject = subject_name

    def is_concurrency_safe(self):
        return False

    def is_persistent(self):
        return True

    async def load(self):
        """Load all properties"""
        if self._subject not in self._storage:
            return {}, {}

        data = self._storage[self._subject]
        return data.get(PropertyType.DEFAULT, {}).copy(), data.get(PropertyType.EXTENDED, {}).copy()

    async def store(self, inserts=[], updates=[], deletes=[]):
        """Store batch operations"""
        if self._subject not in self._storage:
            self._storage[self._subject] = {
                PropertyType.DEFAULT: {},
                PropertyType.EXTENDED: {}
            }

        data = self._storage[self._subject]

        # Apply inserts and updates
        for prop in list(inserts) + list(updates):
            prop_type = prop.type
            data[prop_type][prop.name] = prop.get_value()

        # Apply deletes
        for prop in deletes:
            prop_type = prop.type
            if prop.name in data[prop_type]:
                del data[prop_type][prop.name]

    async def get(self, prop):
        """Get single property"""
        if self._subject not in self._storage:
            raise AttributeError(prop.name)

        data = self._storage[self._subject]
        prop_type = prop.type

        if prop.name not in data[prop_type]:
            raise AttributeError(prop.name)

        return data[prop_type][prop.name]

    async def set(self, prop, old_value_default=None):
        """Set single property"""
        if self._subject not in self._storage:
            self._storage[self._subject] = {
                PropertyType.DEFAULT: {},
                PropertyType.EXTENDED: {}
            }

        data = self._storage[self._subject]
        prop_type = prop.type

        # Get old value
        old_value = data[prop_type].get(prop.name, old_value_default)

        # Handle callable
        value = prop.value
        if callable(value):
            if inspect.isfunction(value):
                n_params = len(inspect.signature(value).parameters)
                if n_params == 0:
                    value = value()
                elif n_params == 1:
                    value = value(old_value)
                else:
                    raise ValueError(f"Callable must take 0 or 1 arguments")

        # Set new value
        data[prop_type][prop.name] = value

        return value, old_value

    async def delete(self, prop):
        """Delete single property"""
        if self._subject not in self._storage:
            raise AttributeError(prop.name)

        data = self._storage[self._subject]
        prop_type = prop.type

        if prop.name not in data[prop_type]:
            raise AttributeError(prop.name)

        del data[prop_type][prop.name]

    async def get_ext_props(self):
        """Get all extended properties"""
        if self._subject not in self._storage:
            return {}

        data = self._storage[self._subject]
        return data.get(PropertyType.EXTENDED, {}).copy()

    async def flush(self):
        """Delete subject"""
        if self._subject in self._storage:
            del self._storage[self._subject]
        return self

    @classmethod
    def clear_all(cls):
        """Clear all storage (for test isolation)"""
        cls._storage.clear()


def create_test_storage():
    """Factory function for creating InMemoryTestStorage instances"""
    def storage_factory(name, **kwargs):
        return InMemoryTestStorage(name)
    return storage_factory
