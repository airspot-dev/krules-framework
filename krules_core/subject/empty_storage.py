class EmptySubjectStorage:

    def is_concurrency_safe(self):

        return False

    def is_persistent(self):

        return False

    def load(self):
        return {}, {}

    def store(self, inserts=[], updates=[], deletes=[]):
        pass

    def set(self, prop, old_value_default=None):

        return None, None

    def get(self, prop):

        return None

    def delete(self, prop):
        pass

    def get_ext_props(self):

        return {}

    def flush(self):

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
