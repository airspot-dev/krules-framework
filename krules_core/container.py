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
from krules_core.subject.empty_storage import create_empty_storage
from krules_core.subject.storaged_subject import Subject
from krules_core.event_bus import EventBus
from krules_core.handlers import create_handlers


class KRulesContainer(containers.DeclarativeContainer):

    config = providers.Configuration()

    # Event Bus
    # Singleton instance for event dispatch across the application
    # Must be defined FIRST (used by subject and decorators)
    event_bus = providers.Singleton(EventBus)

    # Subject Storage Factory
    # This is a CALLABLE that creates storage instances (not a storage instance itself)
    # Subject.__init__ calls: storage(name, event_info, event_data)
    # Default: create_empty_storage() factory function (for testing/development)
    # Override with callable for production (Redis example):
    #   from redis_subjects_storage.storage_impl import create_redis_storage
    #   redis_factory = create_redis_storage("redis://localhost:6379", "myapp:")
    #   container.subject_storage.override(providers.Object(redis_factory))
    subject_storage = providers.Callable(create_empty_storage)

    # Subject Factory
    # Creates Subject instances with injected storage factory and event_bus dependencies
    # storage is a CALLABLE (class or function), not an instance
    subject = providers.Factory(
        Subject,
        storage=subject_storage,
        event_bus=event_bus
    )

    # Handlers Factory
    # Creates @on, @when, @middleware decorators and emit() function bound to the event bus
    # Returns tuple: (on, when, middleware, emit)
    # Note: despite the name, emit is a function not a decorator
    handlers = providers.Callable(
        create_handlers,
        event_bus=event_bus
    )

