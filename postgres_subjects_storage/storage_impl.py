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

import json
import asyncio
import asyncpg

import logging
logger = logging.getLogger(__name__)

from krules_core.subject import PropertyType


class SubjectsPostgresStorage:
    """
    PostgreSQL-based storage for KRules subjects using JSONB columns.

    Schema auto-creation on first use (idempotent, thread-safe).
    Supports callable values with atomic read-modify-write using SELECT FOR UPDATE.
    """

    # Class-level schema initialization tracking (per pool)
    _schema_initialized = {}
    _init_locks = {}

    def __init__(self, subject, pool):
        """
        Initialize PostgreSQL storage for a subject.

        Args:
            subject: Subject name (string)
            pool: asyncpg connection pool
        """
        self._subject = str(subject)
        self._pool = pool

    def __str__(self):
        return "{} instance for {}".format(self.__class__, self._subject)

    def is_concurrency_safe(self):
        """PostgreSQL with row-level locks is concurrency safe"""
        return True

    def is_persistent(self):
        """PostgreSQL storage is persistent"""
        return True

    async def _ensure_schema(self):
        """
        Ensure database schema exists (idempotent, thread-safe).

        Creates 'subjects' table with JSONB columns on first call per pool.
        Uses class-level lock to prevent concurrent schema creation.
        """
        pool_id = id(self._pool)

        # Fast path: already initialized
        if pool_id in SubjectsPostgresStorage._schema_initialized:
            return

        # Get or create lock for this pool
        if pool_id not in SubjectsPostgresStorage._init_locks:
            SubjectsPostgresStorage._init_locks[pool_id] = asyncio.Lock()

        async with SubjectsPostgresStorage._init_locks[pool_id]:
            # Double-check after acquiring lock
            if pool_id in SubjectsPostgresStorage._schema_initialized:
                return

            async with self._pool.acquire() as conn:
                # Create subjects table
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS subjects (
                        subject_name TEXT PRIMARY KEY,
                        properties JSONB NOT NULL DEFAULT '{}',
                        ext_properties JSONB NOT NULL DEFAULT '{}',
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                """)

                # Create GIN indexes for JSONB columns
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_subjects_properties
                    ON subjects USING GIN (properties)
                """)

                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_subjects_ext_properties
                    ON subjects USING GIN (ext_properties)
                """)

                logger.info(f"PostgreSQL schema initialized for pool {pool_id}")

            SubjectsPostgresStorage._schema_initialized[pool_id] = True

    async def load(self):
        """
        Load all properties for the subject.

        Returns:
            Tuple (default_props, ext_props) where each is a dict
        """
        await self._ensure_schema()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT properties, ext_properties FROM subjects WHERE subject_name = $1",
                self._subject
            )

        if row is None:
            return {}, {}

        # asyncpg returns JSONB as JSON string - deserialize to dict
        properties = json.loads(row['properties']) if isinstance(row['properties'], str) else row['properties']
        ext_properties = json.loads(row['ext_properties']) if isinstance(row['ext_properties'], str) else row['ext_properties']
        return properties, ext_properties

    async def store(self, inserts=[], updates=[], deletes=[]):
        """
        Batch store operations for properties.

        Args:
            inserts: List of Property objects to insert
            updates: List of Property objects to update
            deletes: List of Property objects to delete
        """
        if len(inserts) + len(updates) + len(deletes) == 0:
            return

        await self._ensure_schema()

        # Group operations by property type (default vs extended)
        default_updates = {}
        ext_updates = {}
        default_deletes = []
        ext_deletes = []

        # Combine inserts and updates (same operation in PostgreSQL)
        for prop in tuple(inserts) + tuple(updates):
            value = json.loads(prop.json_value())
            if prop.type == PropertyType.DEFAULT:
                default_updates[prop.name] = value
            else:  # PropertyType.EXTENDED
                ext_updates[prop.name] = value

        # Collect deletes
        for prop in deletes:
            if prop.type == PropertyType.DEFAULT:
                default_deletes.append(prop.name)
            else:
                ext_deletes.append(prop.name)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # UPSERT with JSONB merge and delete operations
                if default_updates or ext_updates or default_deletes or ext_deletes:
                    # Build JSONB merge objects as JSON strings
                    default_merge = json.dumps(default_updates) if default_updates else '{}'
                    ext_merge = json.dumps(ext_updates) if ext_updates else '{}'

                    # Build delete arrays
                    default_del_array = default_deletes if default_deletes else []
                    ext_del_array = ext_deletes if ext_deletes else []

                    # UPSERT with merge (asyncpg automatically handles JSON string -> JSONB)
                    if default_updates or ext_updates:
                        await conn.execute("""
                            INSERT INTO subjects (subject_name, properties, ext_properties)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (subject_name) DO UPDATE SET
                                properties = subjects.properties || $2,
                                ext_properties = subjects.ext_properties || $3,
                                updated_at = NOW()
                        """, self._subject, default_merge, ext_merge)

                    # Delete properties (remove keys from JSONB)
                    if default_deletes:
                        await conn.execute("""
                            UPDATE subjects
                            SET properties = properties - $2::text[],
                                updated_at = NOW()
                            WHERE subject_name = $1
                        """, self._subject, default_del_array)

                    if ext_deletes:
                        await conn.execute("""
                            UPDATE subjects
                            SET ext_properties = ext_properties - $2::text[],
                                updated_at = NOW()
                            WHERE subject_name = $1
                        """, self._subject, ext_del_array)

    async def set(self, prop, old_value_default=None):
        """
        Set a single property value atomically.

        Supports callable values with SELECT FOR UPDATE for atomic read-modify-write.

        Args:
            prop: Property object with name, type, and value (can be callable)
            old_value_default: Default value if property doesn't exist

        Returns:
            Tuple (new_value, old_value)
        """
        await self._ensure_schema()

        json_field = 'properties' if prop.type == PropertyType.DEFAULT else 'ext_properties'

        if callable(prop.value):
            # Callable: atomic read-modify-write with SELECT FOR UPDATE
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # Lock row for update
                    row = await conn.fetchrow(
                        f"SELECT {json_field} FROM subjects WHERE subject_name = $1 FOR UPDATE",
                        self._subject
                    )

                    # Get old value (asyncpg returns JSONB as JSON string)
                    if row is None:
                        old_value = old_value_default
                    else:
                        props = json.loads(row[json_field]) if isinstance(row[json_field], str) else row[json_field]
                        old_value = props.get(prop.name, old_value_default)

                    # Compute new value using callable
                    new_value_json = prop.json_value(old_value)
                    new_value = json.loads(new_value_json)

                    # Build JSONB object to merge
                    merge_obj = json.dumps({prop.name: new_value})

                    # UPSERT with new value
                    await conn.execute(f"""
                        INSERT INTO subjects (subject_name, {json_field})
                        VALUES ($1, $2)
                        ON CONFLICT (subject_name) DO UPDATE SET
                            {json_field} = subjects.{json_field} || $2,
                            updated_at = NOW()
                    """, self._subject, merge_obj)

                    return new_value, old_value
        else:
            # Non-callable: simple set
            async with self._pool.acquire() as conn:
                # Get old value first
                row = await conn.fetchrow(
                    f"SELECT {json_field} FROM subjects WHERE subject_name = $1",
                    self._subject
                )

                if row is None:
                    old_value = old_value_default
                else:
                    props = json.loads(row[json_field]) if isinstance(row[json_field], str) else row[json_field]
                    old_value = props.get(prop.name, old_value_default)

                # Set new value
                new_value_json = prop.json_value()
                new_value = prop.get_value()

                # Build JSONB object to merge
                merge_obj = json.dumps({prop.name: new_value})

                await conn.execute(f"""
                    INSERT INTO subjects (subject_name, {json_field})
                    VALUES ($1, $2)
                    ON CONFLICT (subject_name) DO UPDATE SET
                        {json_field} = subjects.{json_field} || $2,
                        updated_at = NOW()
                """, self._subject, merge_obj)

                return new_value, old_value

    async def get(self, prop):
        """
        Get a single property value.

        Args:
            prop: Property object with name and type

        Returns:
            Property value

        Raises:
            AttributeError: If property doesn't exist
        """
        await self._ensure_schema()

        json_field = 'properties' if prop.type == PropertyType.DEFAULT else 'ext_properties'

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {json_field} FROM subjects WHERE subject_name = $1",
                self._subject
            )

        if row is None:
            raise AttributeError(prop.name)

        # Deserialize JSONB
        props = json.loads(row[json_field]) if isinstance(row[json_field], str) else row[json_field]

        if prop.name not in props:
            raise AttributeError(prop.name)

        return props[prop.name]

    async def delete(self, prop):
        """
        Delete a single property.

        Args:
            prop: Property object with name and type
        """
        await self._ensure_schema()

        json_field = 'properties' if prop.type == PropertyType.DEFAULT else 'ext_properties'

        async with self._pool.acquire() as conn:
            await conn.execute(f"""
                UPDATE subjects
                SET {json_field} = {json_field} - $2,
                    updated_at = NOW()
                WHERE subject_name = $1
            """, self._subject, prop.name)

    async def get_ext_props(self):
        """
        Get all extended properties for the subject.

        Returns:
            Dict of extended properties
        """
        await self._ensure_schema()

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT ext_properties FROM subjects WHERE subject_name = $1",
                self._subject
            )

        if row is None:
            return {}

        # Deserialize JSONB
        ext_props = json.loads(row['ext_properties']) if isinstance(row['ext_properties'], str) else row['ext_properties']
        return ext_props

    async def flush(self):
        """
        Delete entire subject from storage.

        Returns:
            self (for chaining)
        """
        await self._ensure_schema()

        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM subjects WHERE subject_name = $1",
                self._subject
            )

        return self


async def create_postgres_pool(postgres_url: str, pool_min_size: int = 10,
                               pool_max_size: int = 50, command_timeout: float = 5.0):
    """
    Create PostgreSQL connection pool.

    This is a Resource that should be initialized in the Container.

    Args:
        postgres_url: PostgreSQL connection URL (e.g., "postgresql://localhost:5432/krules")
        pool_min_size: Minimum connection pool size
        pool_max_size: Maximum connection pool size
        command_timeout: Command timeout in seconds

    Returns:
        asyncpg.Pool instance

    Example:
        >>> pool = await create_postgres_pool("postgresql://localhost/krules")
    """
    pool = await asyncpg.create_pool(
        dsn=postgres_url,
        min_size=pool_min_size,
        max_size=pool_max_size,
        command_timeout=command_timeout
    )
    logger.info(f"PostgreSQL connection pool created: {postgres_url} "
                f"(min={pool_min_size}, max={pool_max_size})")
    return pool


def create_postgres_storage(pool):
    """
    Factory function for creating PostgreSQL storage instances.

    Args:
        pool: asyncpg connection pool (created via create_postgres_pool)

    Returns:
        Callable that creates SubjectsPostgresStorage instances

    Note:
        The returned factory accepts:
        - name (positional): subject name
        - event_info, event_data (kwargs): ignored, accepted for compatibility

    Example:
        >>> pool = await create_postgres_pool("postgresql://localhost/krules")
        >>> storage_factory = create_postgres_storage(pool)
        >>> storage = storage_factory("user-123")
    """
    def storage_factory(name, **kwargs):
        """
        Create PostgreSQL storage instance for a subject.

        Args:
            name: Subject name (positional)
            **kwargs: Ignored (event_info, event_data, etc.)
        """
        return SubjectsPostgresStorage(
            subject=name,
            pool=pool
        )

    return storage_factory
