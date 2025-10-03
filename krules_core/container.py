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
Dependency Injection Container for KRules 2.0

Provides declarative configuration of KRules core dependencies.
Applications can override providers to customize behavior (storage, event bus, etc.).

Example:
    from krules_core.container import KRulesContainer
    from redis_subjects_storage.storage_impl import SubjectsRedisStorage

    class AppContainer(containers.DeclarativeContainer):
        # Create Redis storage
        redis_storage = providers.Factory(
            SubjectsRedisStorage,
            redis_url="redis://localhost:6379",
            key_prefix="myapp->"
        )

        # Create KRules sub-container
        krules = providers.Container(KRulesContainer)

        # Override storage (declarative)
        krules.subject_storage.override(redis_storage)
"""

from dependency_injector import containers, providers
from .subject.empty_storage import EmptySubjectStorage
from .subject.storaged_subject import Subject
from .event_bus import EventBus


def _create_decorators(event_bus):
    """
    Factory function for creating @on and @when decorators bound to an event bus.

    This function is injected with an EventBus instance and returns decorator
    functions that register handlers on that specific bus.

    Args:
        event_bus: EventBus instance (injected by container)

    Returns:
        tuple: (on, when) decorator functions

    Example:
        # In container
        decorators = providers.Callable(_create_decorators, event_bus=event_bus)

        # In handlers
        on, when = container.krules.decorators()
    """
    def on(*event_patterns):
        """
        Register handler on the injected event bus.

        Args:
            *event_patterns: Event patterns to match (supports glob)

        Example:
            @on("user.login")
            @on("user.*")  # Glob pattern
            async def handler(ctx): pass
        """
        def decorator(func):
            pending_filters = getattr(func, "_krules_pending_filters", [])
            handler = event_bus.register(func, list(event_patterns), filters=pending_filters)
            func._krules_handler = handler

            if hasattr(func, "_krules_pending_filters"):
                delattr(func, "_krules_pending_filters")

            return func

        return decorator

    def when(*conditions):
        """
        Add filter conditions to handler.

        Must be used with @on decorator. Multiple @when can be stacked.

        Args:
            *conditions: Filter functions returning bool

        Example:
            @on("user.login")
            @when(lambda ctx: ctx.subject.get("active"))
            @when(lambda ctx: ctx.payload.get("role") == "admin")
            async def handler(ctx): pass
        """
        def decorator(func):
            if hasattr(func, "_krules_handler"):
                # Handler already registered - add filters directly
                func._krules_handler.filters.extend(conditions)
            else:
                # Store pending filters (for when @when is before @on)
                if not hasattr(func, "_krules_pending_filters"):
                    func._krules_pending_filters = []
                func._krules_pending_filters.extend(conditions)

            return func

        return decorator

    return on, when


class KRulesContainer(containers.DeclarativeContainer):
    """
    Container for KRules 2.0 core dependencies.

    Provides default implementations that can be overridden by applications:
    - subject_storage: Default EmptySubjectStorage (in-memory, for testing)
    - subject_factory: Factory for creating Subject instances
    - event_bus: Singleton EventBus for event dispatch

    Applications should override subject_storage to use persistent storage
    (Redis, SQLite, PostgreSQL, etc.).

    Attributes:
        subject_storage: Factory provider for subject storage backend
        subject_factory: Factory provider for creating subjects
        event_bus: Singleton provider for the global event bus
    """

    # Event Bus
    # Singleton instance for event dispatch across the application
    # Must be defined FIRST (used by subject and decorators)
    event_bus = providers.Singleton(EventBus)

    # Subject Storage Factory
    # Default: EmptySubjectStorage (in-memory, ephemeral)
    # Applications SHOULD override this with Redis, SQLite, etc.
    subject_storage = providers.Factory(EmptySubjectStorage)

    # Subject Factory
    # Creates Subject instances with injected storage and event_bus dependencies
    # Both are passed explicitly following dependency injection pattern
    subject = providers.Factory(
        Subject,
        storage=subject_storage,
        event_bus=event_bus
    )

    # Decorators Factory
    # Creates @on and @when decorators bound to the event bus (dependency injected)
    decorators = providers.Callable(
        _create_decorators,
        event_bus=event_bus
    )

