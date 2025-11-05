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
Pytest fixtures for postgres_subjects_storage tests.

Uses local PostgreSQL instance (postgresql://localhost:5432/krules_test).
Requires pytest-asyncio for async test support.
"""

import pytest
import pytest_asyncio
import asyncpg


# PostgreSQL configuration for local testing
POSTGRES_URL = "postgresql://localhost:5432/krules_test"


@pytest.fixture(scope="session")
def postgres_url():
    """PostgreSQL URL for local testing."""
    return POSTGRES_URL


@pytest_asyncio.fixture
async def postgres_pool():
    """
    Create PostgreSQL connection pool for testing.

    Automatically creates 'krules_test' database if it doesn't exist.
    """
    # First, connect to default 'postgres' database to create test database
    try:
        sys_conn = await asyncpg.connect("postgresql://localhost:5432/postgres")
        try:
            # Check if test database exists
            exists = await sys_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = 'krules_test'"
            )
            if not exists:
                # Create test database
                await sys_conn.execute("CREATE DATABASE krules_test")
        finally:
            await sys_conn.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available at localhost:5432: {e}")

    # Create connection pool to test database
    try:
        pool = await asyncpg.create_pool(
            dsn=POSTGRES_URL,
            min_size=2,
            max_size=10,
            command_timeout=5.0
        )
    except Exception as e:
        pytest.skip(f"Cannot create PostgreSQL pool: {e}")

    yield pool

    # Cleanup: close pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_postgres(postgres_pool):
    """Clean up subjects table before and after each test."""
    from postgres_subjects_storage.storage_impl import SubjectsPostgresStorage

    # Pre-cleanup: drop table and reset schema initialization flag
    async with postgres_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS subjects CASCADE")

    # Reset schema initialization flag for this pool
    pool_id = id(postgres_pool)
    if pool_id in SubjectsPostgresStorage._schema_initialized:
        del SubjectsPostgresStorage._schema_initialized[pool_id]

    yield

    # Post-cleanup: drop table and reset flag
    async with postgres_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS subjects CASCADE")

    if pool_id in SubjectsPostgresStorage._schema_initialized:
        del SubjectsPostgresStorage._schema_initialized[pool_id]


@pytest.fixture
def subject_name(request):
    """Test subject name (unique per test)."""
    test_name = request.node.name
    return f"test-{test_name}"


@pytest_asyncio.fixture
async def postgres_storage(postgres_pool, subject_name):
    """Create SubjectsPostgresStorage instance for testing."""
    from postgres_subjects_storage.storage_impl import SubjectsPostgresStorage

    return SubjectsPostgresStorage(
        subject=subject_name,
        pool=postgres_pool
    )


@pytest.fixture
def postgres_storage_factory(postgres_pool):
    """Factory for creating multiple storage instances."""
    from postgres_subjects_storage.storage_impl import SubjectsPostgresStorage

    def factory(subject_name: str):
        return SubjectsPostgresStorage(
            subject=subject_name,
            pool=postgres_pool
        )

    return factory
