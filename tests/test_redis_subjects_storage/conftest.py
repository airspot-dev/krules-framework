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
Requires pytest-asyncio for async test support.
"""

import pytest
import pytest_asyncio
from redis.asyncio import Redis


# Redis configuration for local testing
REDIS_URL = "redis://localhost:6379/0"
TEST_KEY_PREFIX = "test:"


@pytest.fixture(scope="session")
def redis_url():
    """Redis URL for local testing."""
    return REDIS_URL


@pytest_asyncio.fixture
async def redis_client():
    """
    Create async Redis client for testing.

    Automatically skips if Redis is not available.
    """
    client = Redis.from_url(REDIS_URL, decode_responses=False)

    # Verify connection
    try:
        await client.ping()
    except Exception as e:
        pytest.skip(f"Redis not available at localhost:6379: {e}")

    yield client

    # Cleanup: close connection
    await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_redis(redis_client):
    """Clean up test keys before and after each test."""
    # Pre-cleanup: remove all test keys (Redis keys are formatted as s:{prefix}{subject})
    keys = []
    async for key in redis_client.scan_iter(f"s:{TEST_KEY_PREFIX}*"):
        keys.append(key)
    # Also clean any "other:" prefix keys used in isolation tests
    async for key in redis_client.scan_iter("s:other:*"):
        keys.append(key)
    if keys:
        await redis_client.delete(*keys)

    yield

    # Post-cleanup: remove all test keys
    keys = []
    async for key in redis_client.scan_iter(f"s:{TEST_KEY_PREFIX}*"):
        keys.append(key)
    async for key in redis_client.scan_iter("s:other:*"):
        keys.append(key)
    if keys:
        await redis_client.delete(*keys)


@pytest.fixture
def subject_name(request):
    """Test subject name (unique per test)."""
    # Use test name to create unique subject for each test
    test_name = request.node.name
    return f"test-{test_name}"


@pytest_asyncio.fixture
async def redis_storage(redis_client, subject_name):
    """Create SubjectsRedisStorage instance for testing."""
    from redis_subjects_storage.storage_impl import SubjectsRedisStorage

    return SubjectsRedisStorage(
        subject=subject_name,
        redis_client=redis_client,
        key_prefix=TEST_KEY_PREFIX
    )


@pytest.fixture
def redis_storage_factory(redis_client):
    """Factory for creating multiple storage instances."""
    from redis_subjects_storage.storage_impl import SubjectsRedisStorage

    def factory(subject_name: str):
        return SubjectsRedisStorage(
            subject=subject_name,
            redis_client=redis_client,
            key_prefix=TEST_KEY_PREFIX
        )
    return factory
