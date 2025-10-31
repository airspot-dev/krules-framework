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
Tests for KrulesApp initialization and configuration.
"""

import pytest
from fastapi import FastAPI
from krules_fastapi_env import KrulesApp


class TestKrulesAppInitialization:
    """Test suite for KrulesApp initialization"""

    def test_app_is_fastapi_instance(self, krules_app):
        """KrulesApp should be a FastAPI instance."""
        assert isinstance(krules_app, FastAPI)

    def test_app_receives_krules_container(self, krules_app, krules_container):
        """KrulesApp should store krules_container reference."""
        assert krules_app._krules is krules_container

    def test_app_with_custom_title(self, krules_container):
        """KrulesApp should accept FastAPI kwargs."""
        app = KrulesApp(
            krules_container=krules_container,
            title="Custom Title",
            version="1.0.0"
        )
        assert app.title == "Custom Title"
        assert app.version == "1.0.0"

    def test_app_default_cloudevents_path(self, krules_app):
        """KrulesApp should register CloudEvents endpoint at / by default."""
        routes = [route.path for route in krules_app.routes]
        assert "/" in routes

    def test_app_custom_cloudevents_path(self, krules_app_custom_path):
        """KrulesApp should support custom CloudEvents endpoint path."""
        routes = [route.path for route in krules_app_custom_path.routes]
        assert "/events" in routes
