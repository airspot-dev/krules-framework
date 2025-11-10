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
from redis.asyncio import Redis

import logging
logger = logging.getLogger(__name__)

from krules_core.subject import PropertyType


class SubjectsRedisStorage:
    """
    Async Redis storage for KRules subjects.

    Uses redis.asyncio for full async/await support.
    """

    def __init__(self, subject, redis_client, key_prefix=""):
        """
        Initialize Redis storage for a subject.

        Args:
            subject: Subject name (string)
            redis_client: redis.asyncio.Redis client instance
            key_prefix: Optional key prefix for Redis keys
        """
        self._subject = str(subject)
        self._conn = redis_client
        self._key_prefix = key_prefix

    def __str__(self):
        return "{} instance for {}".format(self.__class__, self._subject)

    def is_concurrency_safe(self):
        """Redis WATCH/MULTI/EXEC provides concurrency safety"""
        return True

    def is_persistent(self):
        """Redis storage is persistent (with RDB/AOF)"""
        return True

    async def load(self):
        """
        Load all properties for the subject.

        Returns:
            Tuple (default_props, ext_props) where each is a dict
        """
        res = {
            PropertyType.DEFAULT: {},
            PropertyType.EXTENDED: {}
        }
        hset = await self._conn.hgetall(f"s:{self._key_prefix}{self._subject}")
        for k, v in hset.items():
            k = k.decode("utf-8")
            res[k[0]][k[1:]] = json.loads(v)
        return res[PropertyType.DEFAULT], res[PropertyType.EXTENDED]

    async def store(self, inserts=[], updates=[], deletes=[]):
        """
        Batch store operations for properties.

        Args:
            inserts: List of Property objects to insert
            updates: List of Property objects to update
            deletes: List of Property objects to delete
        """
        if len(inserts)+len(updates)+len(deletes) == 0:
            return

        skey = f"s:{self._key_prefix}{self._subject}"
        hset = {}
        for prop in tuple(inserts)+tuple(updates):
            hset[f"{prop.type}{prop.name}"] = prop.json_value()
        async with self._conn.pipeline() as pipe:
            # Only call hset if there are properties to set
            if hset:
                pipe.hset(skey, mapping=hset)
            for pkey in [f"{el.type}{el.name}" for el in deletes]:
                pipe.hdel(skey, pkey)
            await pipe.execute()


    async def set(self, prop, old_value_default=None):
        """
        Set a single property value atomically.

        Supports callable values with WATCH/MULTI/EXEC for atomic read-modify-write.

        Args:
            prop: Property object with name, type, and value (can be callable)
            old_value_default: Default value if property doesn't exist

        Returns:
            Tuple (new_value, old_value)
        """
        from redis.asyncio import WatchError

        skey = f"s:{self._key_prefix}{self._subject}"
        pname = f"{prop.type}{prop.name}"
        if callable(prop.value):
            # Callable: atomic read-modify-write with WATCH/MULTI/EXEC
            while True:
                try:
                    async with self._conn.pipeline() as pipe:
                        await pipe.watch(skey)
                        old_value = await pipe.hget(skey, pname)
                        pipe.multi()
                        if old_value is None:
                            old_value = old_value_default
                        else:
                            old_value = json.loads(old_value)
                        new_value = prop.json_value(old_value)
                        pipe.hset(skey, pname, new_value)
                        await pipe.execute()
                        break
                except WatchError:
                    continue
            new_value = json.loads(new_value)
        else:
            # Non-callable: simple set
            async with self._conn.pipeline() as pipe:
                pipe.hget(skey, pname)
                pipe.hset(skey, pname, prop.json_value())
                old_value, _ = await pipe.execute()
                if old_value is None:
                    old_value = old_value_default
                else:
                    old_value = json.loads(old_value)

                new_value = prop.get_value()

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
        skey = f"s:{self._key_prefix}{self._subject}"
        pname = f"{prop.type}{prop.name}"
        async with self._conn.pipeline() as pipe:
            pipe.hexists(skey, pname)
            pipe.hget(skey, pname)
            exists, value = await pipe.execute()
        if not exists:
            raise AttributeError(prop.name)
        return json.loads(value)

    async def delete(self, prop):
        """
        Delete a single property.

        Args:
            prop: Property object with name and type
        """
        skey = f"s:{self._key_prefix}{self._subject}"
        pname = f"{prop.type}{prop.name}"
        await self._conn.hdel(skey, pname)

    async def get_ext_props(self):
        """
        Get all extended properties for the subject.

        Returns:
            Dict of extended properties
        """
        props = {}
        skey = f"s:{self._key_prefix}{self._subject}"
        async for pname, pval in self._conn.hscan_iter(skey, f"{PropertyType.EXTENDED}*"):
            props[pname[1:].decode("utf-8")] = json.loads(pval)
        return props

    async def flush(self):
        """
        Delete entire subject from storage.

        Returns:
            self (for chaining)
        """
        skey = f"s:{self._key_prefix}{self._subject}"
        await self._conn.delete(skey)
        return self


async def create_redis_client(redis_url: str):
    """
    Create async Redis client.

    This is a Resource that should be initialized in the Container.

    Args:
        redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")

    Returns:
        redis.asyncio.Redis instance

    Example:
        >>> client = await create_redis_client("redis://localhost:6379/0")
    """
    client = Redis.from_url(redis_url, decode_responses=False)
    logger.info(f"Redis async client created: {redis_url}")
    return client


def create_redis_storage(redis_client, redis_prefix: str = ""):
    """
    Factory function for creating Redis storage instances.

    Args:
        redis_client: redis.asyncio.Redis client instance (created via create_redis_client)
        redis_prefix: Key prefix for Redis keys

    Returns:
        Callable that creates SubjectsRedisStorage instances

    Note:
        The returned factory accepts:
        - name (positional): subject name
        - event_info, event_data (kwargs): ignored, accepted for compatibility

    Example:
        >>> client = await create_redis_client("redis://localhost:6379/0")
        >>> storage_factory = create_redis_storage(client, redis_prefix="myapp:")
        >>> storage = storage_factory("user-123")
    """

    def storage_factory(name, **kwargs):
        """
        Create Redis storage instance for a subject.

        Args:
            name: Subject name (positional)
            **kwargs: Ignored (event_info, event_data, etc.)
        """
        return SubjectsRedisStorage(
            subject=name,
            redis_client=redis_client,
            key_prefix=redis_prefix
        )

    return storage_factory

