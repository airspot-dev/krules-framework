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
Dependency injection providers for KRules 2.0

Simplified provider system - removed ReactiveX and rule system dependencies.
Only provides essential factories for Subject and storage.
"""

from dependency_injector import providers as di_providers
from krules_core.subject.empty_storage import EmptySubjectStorage
from .subject.storaged_subject import Subject

# Configuration factory (for application config)
configs_factory = di_providers.Singleton(lambda: {})

# Subject storage factory (default: EmptySubjectStorage for testing/development)
# Override with Redis, SQLite, etc. in production
subject_storage_factory = di_providers.Factory(
    lambda *args, **kwargs: EmptySubjectStorage()
)

# Subject factory
subject_factory = di_providers.Factory(Subject)