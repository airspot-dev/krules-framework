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
Tests for KRules configuration system (settings)
"""

import os
import pytest
from krules_core.settings import KRulesSettings, StorageRedisSettings


@pytest.fixture(autouse=True)
def clean_env():
    """Clean all KRULES and SUBJECTS env vars before and after each test"""
    # Save original values
    original_env = {}

    # Get all env vars starting with KRULES_ or SUBJECTS_
    keys_to_clean = [
        key for key in os.environ.keys()
        if key.startswith("KRULES_") or key.startswith("SUBJECTS_")
    ]

    # Save and remove them
    for key in keys_to_clean:
        original_env[key] = os.environ.pop(key)

    yield

    # Clean up any vars set during test
    keys_to_clean_after = [
        key for key in os.environ.keys()
        if key.startswith("KRULES_") or key.startswith("SUBJECTS_")
    ]
    for key in keys_to_clean_after:
        os.environ.pop(key, None)

    # Restore original values
    for key, value in original_env.items():
        os.environ[key] = value


class TestKRulesSettings:
    """Test suite for KRules configuration system"""

    def test_legacy_subjects_redis_url(self):
        """Backward compatibility with SUBJECTS_REDIS_URL"""
        os.environ["SUBJECTS_REDIS_URL"] = "redis://legacy-host:6379/0"

        settings = KRulesSettings()

        # Auto-detected as redis because legacy URL is set
        assert settings.storage_provider == "redis"
        assert settings.storage_redis.url == "redis://legacy-host:6379/0"

    def test_legacy_url_takes_precedence(self):
        """Legacy SUBJECTS_REDIS_URL takes precedence over component settings"""
        os.environ["SUBJECTS_REDIS_URL"] = "redis://legacy-host:6379/0"
        os.environ["KRULES_STORAGE_REDIS_HOST"] = "new-host"

        settings = KRulesSettings()

        # Legacy URL should be used
        assert settings.storage_redis.url == "redis://legacy-host:6379/0"

    def test_explicit_storage_provider_override(self):
        """Explicit provider overrides auto-detection"""
        os.environ["KRULES_STORAGE_PROVIDER"] = "empty"
        os.environ["KRULES_STORAGE_REDIS_HOST"] = "localhost"

        settings = KRulesSettings()

        # Explicit override to empty
        assert settings.storage_provider == "empty"
        # Redis config is still parsed but not used
        assert settings.storage_redis.host == "localhost"


class TestStorageRedisSettings:
    """Test suite for Redis-specific settings"""

    def test_redis_settings_defaults(self):
        """Redis settings have correct defaults"""
        settings = StorageRedisSettings()

        assert settings.host is None
        assert settings.port == 6379
        assert settings.db == 0
        assert settings.password is None
        assert settings.use_tls is False
        assert settings.key_prefix == ""

    def test_redis_url_none_without_host(self):
        """URL is None when host is not configured"""
        settings = StorageRedisSettings()

        assert settings.url is None

    def test_redis_url_construction(self):
        """URL is correctly constructed from components"""
        settings = StorageRedisSettings(
            host="testhost",
            port=6380,
            db=2,
            password="pass123"
        )

        assert settings.url == "redis://:pass123@testhost:6380/2"

    def test_redis_url_with_tls(self):
        """URL uses rediss:// protocol with TLS"""
        settings = StorageRedisSettings(
            host="secure.redis.com",
            use_tls=True
        )

        assert settings.url == "rediss://secure.redis.com:6379/0"
