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
Pytest fixtures for redis_subjects_storage tests.

Uses local Redis instance (redis://localhost:6379/0).
"""

import pytest
import redis


# Redis configuration for local testing
REDIS_URL = "redis://localhost:6379/0"
TEST_KEY_PREFIX = "test:"


@pytest.fixture(scope="session")
def redis_url():
    """Redis URL for local testing."""
    return REDIS_URL


@pytest.fixture(scope="session")
def redis_connection():
    """Create Redis connection for testing."""
    conn = redis.Redis.from_url(REDIS_URL)

    # Verify connection
    try:
        conn.ping()
    except redis.ConnectionError:
        pytest.skip("Redis not available at localhost:6379")

    return conn


@pytest.fixture(autouse=True)
def cleanup_redis(redis_connection):
    """Clean up test keys before and after each test."""
    # Pre-cleanup: remove all test keys (Redis keys are formatted as s:{prefix}{subject})
    for key in redis_connection.scan_iter(f"s:{TEST_KEY_PREFIX}*"):
        redis_connection.delete(key)
    # Also clean any "other:" prefix keys used in isolation tests
    for key in redis_connection.scan_iter("s:other:*"):
        redis_connection.delete(key)

    yield

    # Post-cleanup: remove all test keys
    for key in redis_connection.scan_iter(f"s:{TEST_KEY_PREFIX}*"):
        redis_connection.delete(key)
    # Also clean any "other:" prefix keys used in isolation tests
    for key in redis_connection.scan_iter("s:other:*"):
        redis_connection.delete(key)


@pytest.fixture
def subject_name(request):
    """Test subject name (unique per test)."""
    # Use test name to create unique subject for each test
    test_name = request.node.name
    return f"test-{test_name}"


@pytest.fixture
def redis_storage(redis_url, subject_name):
    """Create SubjectsRedisStorage instance for testing."""
    from redis_subjects_storage.storage_impl import SubjectsRedisStorage

    return SubjectsRedisStorage(
        subject=subject_name,
        url=redis_url,
        key_prefix=TEST_KEY_PREFIX
    )


@pytest.fixture
def redis_storage_factory(redis_url):
    """Factory for creating multiple storage instances."""
    from redis_subjects_storage.storage_impl import SubjectsRedisStorage

    def factory(subject_name: str):
        return SubjectsRedisStorage(
            subject=subject_name,
            url=redis_url,
            key_prefix=TEST_KEY_PREFIX
        )
    return factory
