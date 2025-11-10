class EmptySubjectStorage:
    """
    Empty (no-op) async storage for KRules subjects.

    Provides the storage interface but doesn't persist data.
    All storage methods are async for interface consistency.
    """

    def is_concurrency_safe(self):
        """Storage concurrency safety (sync - metadata only)"""
        return False

    def is_persistent(self):
        """Storage persistence (sync - metadata only)"""
        return False

    async def load(self):
        """Load properties (async)"""
        return {}, {}

    async def store(self, inserts=[], updates=[], deletes=[]):
        """Store properties (async)"""
        pass

    async def set(self, prop, old_value_default=None):
        """Set single property (async)"""
        return None, None

    async def get(self, prop):
        """Get single property (async)"""
        return None

    async def delete(self, prop):
        """Delete single property (async)"""
        pass

    async def get_ext_props(self):
        """Get extended properties (async)"""
        return {}

    async def flush(self):
        """Flush subject (async)"""
        return self


def create_empty_storage():
    """
    Factory function for creating EmptySubjectStorage instances.

    Returns a callable that creates EmptySubjectStorage instances.
    The factory accepts name and optional kwargs for compatibility with Subject.__init__.

    Returns:
        Callable that creates EmptySubjectStorage instances
    """
    def storage_factory(name, **kwargs):
        """
        Create EmptySubjectStorage instance for a subject.

        Args:
            name: Subject name (positional, ignored by EmptySubjectStorage)
            **kwargs: Ignored (event_info, event_data, etc.)
        """
        return EmptySubjectStorage()

    return storage_factory
