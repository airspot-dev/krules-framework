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
Pytest fixtures for krules_fastapi_env tests.
"""

import pytest
from krules_core.container import KRulesContainer
from krules_fastapi_env import KrulesApp


@pytest.fixture
def krules_container():
    """Create KRulesContainer instance for testing."""
    container = KRulesContainer()
    yield container
    # Cleanup
    container.unwire()


@pytest.fixture
def krules_app(krules_container):
    """Create KrulesApp for testing."""
    return KrulesApp(
        krules_container=krules_container,
        title="Test KRules API"
    )


@pytest.fixture
def krules_app_custom_path(krules_container):
    """Create KrulesApp with custom CloudEvents endpoint path."""
    return KrulesApp(
        krules_container=krules_container,
        cloudevents_path="/events",
        title="Test KRules API Custom Path"
    )
