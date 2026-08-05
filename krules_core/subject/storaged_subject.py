import inspect
import asyncio

from krules_core.subject import SubjectProperty, SubjectExtProperty, PayloadConst, PropertyType


# Sentinel value to distinguish "default not provided" from "default=None"
_NOT_PROVIDED = object()


class Subject:
    """
    Async Subject implementation for KRules.

    Provides async API for subject property management with transparent caching.
    All methods automatically load cache when needed.

    Example:
        # Use KRulesContainer (recommended)
        from krules_core.container import KRulesContainer
        container = KRulesContainer()

        user = container.subject("user-123")
        await user.set("name", "John")
        name = await user.get("name")
        await user.store()
    """

    def __init__(self, name, storage, event_bus, use_cache_default=True):
        """
        Initialize a Subject.

        Args:
            name: Subject name/identifier
            storage: Storage factory provider (REQUIRED - use KRulesContainer.subject())
            event_bus: EventBus instance (REQUIRED - use KRulesContainer.subject())
            use_cache_default: Whether to use caching by default (default: True)

        Note:
            Direct instantiation is not recommended. Use KRulesContainer.subject() instead.
        """
        if storage is None:
            raise ValueError(
                "storage parameter is required. Use KRulesContainer.subject() instead of "
                "direct Subject instantiation. Example: container.subject('name')"
            )

        if event_bus is None:
            raise ValueError(
                "event_bus parameter is required. Use KRulesContainer.subject() instead of "
                "direct Subject instantiation. Example: container.subject('name')"
            )

        self.name = name
        self._use_cache = use_cache_default
        self._storage = storage(name)
        self._cached = None
        self._event_bus = event_bus

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"Subject<{self.name}>"

    async def _load(self):
        """
        Load properties from storage into cache.

        Automatically called by get/set/has/keys when cache is None.
        """
        props, ext_props = await self._storage.load()
        self._cached = {
            PropertyType.DEFAULT: {
                "values": {},
                "created": set(),
                "updated": set(),
                "deleted": set(),
            },
            PropertyType.EXTENDED: {
                "values": {},
                "created": set(),
                "updated": set(),
                "deleted": set(),
            }
        }
        self._cached[PropertyType.DEFAULT]["values"] = props
        self._cached[PropertyType.EXTENDED]["values"] = ext_props

    async def get(self, prop, default=_NOT_PROVIDED, use_cache=None):
        """
        Get a property value.

        Args:
            prop: Property name
            default: Default value if property doesn't exist
            use_cache: If True, read from cache; if False, read directly from storage;
                       if None, use default from constructor (default: None)

        Returns:
            Property value or default

        Example:
            name = await user.get("name")
            age = await user.get("age", default=0)
            value_or_none = await user.get("maybe", default=None)
            fresh_data = await user.get("data", use_cache=False)  # Read directly from storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache:
            # Cache-based operation
            # Auto-load cache if needed
            if self._cached is None:
                await self._load()

            try:
                return self._cached[PropertyType.DEFAULT]["values"][prop]
            except KeyError:
                if default is not _NOT_PROVIDED:
                    return default
                raise AttributeError(f"Property '{prop}' not found")
        else:
            # Direct storage operation
            try:
                value = await self._storage.get(SubjectProperty(prop))

                # Sync cache if present (never create it). A read must not produce a
                # write obligation, nor overwrite one already pending.
                if self._cached is not None:
                    cache = self._cached[PropertyType.DEFAULT]
                    if prop not in cache["created"] and prop not in cache["updated"]:
                        cache["values"][prop] = value

                return value
            except AttributeError:
                if default is not _NOT_PROVIDED:
                    return default
                raise AttributeError(f"Property '{prop}' not found")

    async def get_ext(self, prop, default=_NOT_PROVIDED, use_cache=None):
        """
        Get an extended property value.

        Args:
            prop: Property name
            default: Default value if property doesn't exist
            use_cache: If True, read from cache; if False, read directly from storage;
                       if None, use default from constructor (default: None)

        Returns:
            Property value or default

        Example:
            tenant = await user.get_ext("tenant_id")
            tags_or_none = await user.get_ext("tags", default=None)
            fresh_tenant = await user.get_ext("tenant_id", use_cache=False)  # Read from storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache:
            # Cache-based operation
            # Auto-load cache if needed
            if self._cached is None:
                await self._load()

            try:
                return self._cached[PropertyType.EXTENDED]["values"][prop]
            except KeyError:
                if default is not _NOT_PROVIDED:
                    return default
                raise AttributeError(f"Extended property '{prop}' not found")
        else:
            # Direct storage operation
            try:
                value = await self._storage.get(SubjectExtProperty(prop))

                # Sync cache if present (never create it). A read must not produce a
                # write obligation, nor overwrite one already pending.
                if self._cached is not None:
                    cache = self._cached[PropertyType.EXTENDED]
                    if prop not in cache["created"] and prop not in cache["updated"]:
                        cache["values"][prop] = value

                return value
            except AttributeError:
                if default is not _NOT_PROVIDED:
                    return default
                raise AttributeError(f"Extended property '{prop}' not found")

    async def set(self, prop, value, muted=False, extra=None, use_cache=None):
        """
        Set a property value.

        The "subject-property-changed" event is emitted ONLY when the new value differs
        from the old one (``value != old_value``) and ``muted`` is False. Re-setting a
        property to its current value still writes the value, but emits no event.
        Note that ``delete()`` behaves differently: it always emits.

        Args:
            prop: Property name
            value: Property value (can be callable for atomic operations)
            muted: If True, never emit the property-changed event
            extra: Optional dict with extra context passed to event handlers
            use_cache: If True, only update cache; if False, write directly to storage;
                       if None, use default from constructor (default: None)

        Returns:
            Tuple (new_value, old_value)

        Example:
            await user.set("name", "John")
            await user.set("counter", lambda c: c + 1)  # Atomic increment
            await user.set("status", "active", extra={"reason": "login"})
            await user.set("temp", "value", use_cache=False)  # Write immediately to storage
            await user.set("name", "John")  # Same value -> no event emitted
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache:
            # Cache-based operation (current behavior)
            # Auto-load cache if needed
            if self._cached is None:
                await self._load()

            # Get old value
            vals = self._cached[PropertyType.DEFAULT]["values"]
            old_value = vals.get(prop)

            # Handle callable values
            if callable(value):
                # For callable, evaluate function with old value
                if inspect.isfunction(value):
                    n_params = len(inspect.signature(value).parameters)
                    if n_params == 0:
                        value = value()
                    elif n_params == 1:
                        value = value(old_value)
                    else:
                        raise ValueError(f"Callable for property '{prop}' must take 0 or 1 arguments")

            # Track changes for store()
            if prop in vals:
                self._cached[PropertyType.DEFAULT]["updated"].add(prop)
            else:
                self._cached[PropertyType.DEFAULT]["created"].add(prop)

            # Set new value in cache
            vals[prop] = value
        else:
            # Direct storage operation (bypass cache)
            value, old_value = await self._storage.set(SubjectProperty(prop, value))

            # Sync cache if present (never create it). The value is already in storage,
            # so the property is clean and must not be left pending for store().
            if self._cached is not None:
                cache = self._cached[PropertyType.DEFAULT]
                cache["values"][prop] = value
                cache["created"].discard(prop)
                cache["updated"].discard(prop)
                cache["deleted"].discard(prop)

        # Emit property-changed event if not muted
        if not muted and value != old_value:
            payload = {
                PayloadConst.PROPERTY_NAME: prop,
                PayloadConst.OLD_VALUE: old_value,
                PayloadConst.VALUE: value
            }
            await self._event_bus.emit("subject-property-changed", self, payload, extra=extra)

        return (value, old_value)

    async def set_ext(self, prop, value, use_cache=None):
        """
        Set an extended property value.

        Extended properties never emit events, whatever the value: they are metadata,
        outside the reactive flow. Use set() for anything handlers should react to.

        Args:
            prop: Property name
            value: Property value
            use_cache: If True, only update cache; if False, write directly to storage;
                       if None, use default from constructor (default: None)

        Returns:
            Tuple (new_value, old_value)

        Example:
            await user.set_ext("tenant_id", "t123")
            await user.set_ext("temp_data", "value", use_cache=False)  # Write immediately
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache:
            # Cache-based operation
            # Auto-load cache if needed
            if self._cached is None:
                await self._load()

            # Get old value
            vals = self._cached[PropertyType.EXTENDED]["values"]
            old_value = vals.get(prop)

            # Track changes for store()
            if prop in vals:
                self._cached[PropertyType.EXTENDED]["updated"].add(prop)
            else:
                self._cached[PropertyType.EXTENDED]["created"].add(prop)

            # Set new value in cache
            vals[prop] = value
        else:
            # Direct storage operation
            value, old_value = await self._storage.set(SubjectExtProperty(prop, value))

            # Sync cache if present (never create it). The value is already in storage,
            # so the property is clean and must not be left pending for store().
            if self._cached is not None:
                cache = self._cached[PropertyType.EXTENDED]
                cache["values"][prop] = value
                cache["created"].discard(prop)
                cache["updated"].discard(prop)
                cache["deleted"].discard(prop)

        return (value, old_value)

    async def delete(self, prop, muted=False, extra=None, use_cache=None):
        """
        Delete a property.

        Unlike set(), deletion emits "subject-property-deleted" on every successful call
        (unless muted): there is no value comparison to skip it.

        Raises:
            AttributeError: if the property does not exist (nothing is emitted)

        Args:
            prop: Property name
            muted: If True, don't emit property-deleted event
            extra: Optional dict with extra context passed to event handlers
            use_cache: If True, only update cache; if False, delete directly from storage;
                       if None, use default from constructor (default: None)

        Example:
            await user.delete("temp_field")
            await user.delete("cache", extra={"reason": "expired"})
            await user.delete("session", use_cache=False)  # Delete immediately from storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache:
            # Cache-based operation
            # Auto-load cache if needed
            if self._cached is None:
                await self._load()

            vals = self._cached[PropertyType.DEFAULT]["values"]

            if prop not in vals:
                raise AttributeError(f"Property '{prop}' not found")

            # Capture old value before deletion
            old_value = vals[prop]

            # Delete from cache
            del vals[prop]

            # Track deletion for store()
            if prop in self._cached[PropertyType.DEFAULT]["created"]:
                self._cached[PropertyType.DEFAULT]["created"].remove(prop)
            if prop in self._cached[PropertyType.DEFAULT]["updated"]:
                self._cached[PropertyType.DEFAULT]["updated"].remove(prop)
            self._cached[PropertyType.DEFAULT]["deleted"].add(prop)
        else:
            # Direct storage operation
            # Get old value first
            try:
                old_value = await self._storage.get(SubjectProperty(prop))
            except AttributeError:
                raise AttributeError(f"Property '{prop}' not found")

            # Delete from storage
            await self._storage.delete(SubjectProperty(prop))

            # Sync cache if present (never create it). The property is already gone from
            # storage, so it is clean and must not be left pending for store().
            if self._cached is not None:
                cache = self._cached[PropertyType.DEFAULT]
                cache["values"].pop(prop, None)
                cache["created"].discard(prop)
                cache["updated"].discard(prop)
                cache["deleted"].discard(prop)

        # Emit property-deleted event if not muted
        if not muted:
            payload = {
                PayloadConst.PROPERTY_NAME: prop,
                PayloadConst.OLD_VALUE: old_value
            }
            await self._event_bus.emit("subject-property-deleted", self, payload, extra=extra)

    async def delete_ext(self, prop, use_cache=None):
        """
        Delete an extended property.

        Args:
            prop: Property name
            use_cache: If True, only update cache; if False, delete directly from storage;
                       if None, use default from constructor (default: None)

        Example:
            await user.delete_ext("tenant_id")
            await user.delete_ext("temp_data", use_cache=False)  # Delete immediately
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache:
            # Cache-based operation
            # Auto-load cache if needed
            if self._cached is None:
                await self._load()

            vals = self._cached[PropertyType.EXTENDED]["values"]

            if prop not in vals:
                raise AttributeError(f"Extended property '{prop}' not found")

            # Delete from cache
            del vals[prop]

            # Track deletion for store()
            if prop in self._cached[PropertyType.EXTENDED]["created"]:
                self._cached[PropertyType.EXTENDED]["created"].remove(prop)
            if prop in self._cached[PropertyType.EXTENDED]["updated"]:
                self._cached[PropertyType.EXTENDED]["updated"].remove(prop)
            self._cached[PropertyType.EXTENDED]["deleted"].add(prop)
        else:
            # Direct storage operation
            # Check if property exists first
            try:
                await self._storage.get(SubjectExtProperty(prop))
            except AttributeError:
                raise AttributeError(f"Extended property '{prop}' not found")

            # Delete from storage
            await self._storage.delete(SubjectExtProperty(prop))

            # Sync cache if present (never create it). The property is already gone from
            # storage, so it is clean and must not be left pending for store().
            if self._cached is not None:
                cache = self._cached[PropertyType.EXTENDED]
                cache["values"].pop(prop, None)
                cache["created"].discard(prop)
                cache["updated"].discard(prop)
                cache["deleted"].discard(prop)

    async def has(self, prop, use_cache=None):
        """
        Check if a property exists.

        Args:
            prop: Property name
            use_cache: If True, check the cache; if False, check storage directly
                       without creating or touching the cache; if None, use the
                       default from the constructor (default: None)

        Returns:
            bool: True if property exists

        Example:
            if await user.has("name"):
                name = await user.get("name")
            fresh = await user.has("name", use_cache=False)  # Ask storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if not use_cache:
            # Direct storage operation: single key, cache left untouched
            try:
                await self._storage.get(SubjectProperty(prop))
                return True
            except AttributeError:
                return False

        # Auto-load cache if needed
        if self._cached is None:
            await self._load()

        return prop in self._cached[PropertyType.DEFAULT]["values"]

    async def has_ext(self, prop, use_cache=None):
        """
        Check if an extended property exists.

        Args:
            prop: Property name
            use_cache: If True, check the cache; if False, check storage directly
                       without creating or touching the cache; if None, use the
                       default from the constructor (default: None)

        Returns:
            bool: True if extended property exists

        Example:
            if await user.has_ext("tenant_id"):
                tenant = await user.get_ext("tenant_id")
            fresh = await user.has_ext("tenant_id", use_cache=False)  # Ask storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if not use_cache:
            # Direct storage operation: single key, cache left untouched
            try:
                await self._storage.get(SubjectExtProperty(prop))
                return True
            except AttributeError:
                return False

        # Auto-load cache if needed
        if self._cached is None:
            await self._load()

        return prop in self._cached[PropertyType.EXTENDED]["values"]

    async def keys(self, use_cache=None):
        """
        Get list of all property names.

        Args:
            use_cache: If True, read from the cache; if False, read from storage
                       without creating or touching the cache; if None, use the
                       default from the constructor (default: None)

        Returns:
            list: Property names

        Example:
            keys = await user.keys()
            for key in keys:
                value = await user.get(key)
            fresh_keys = await user.keys(use_cache=False)  # See other processes' writes
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if not use_cache:
            # Direct storage operation: cache left untouched
            props, _ = await self._storage.load()
            return list(props.keys())

        # Auto-load cache if needed
        if self._cached is None:
            await self._load()

        return list(self._cached[PropertyType.DEFAULT]["values"].keys())

    async def get_ext_props(self, use_cache=None):
        """
        Get all extended properties as dict.

        Args:
            use_cache: If True, read from the cache; if False, read from storage
                       without creating or touching the cache; if None, use the
                       default from the constructor (default: None)

        Returns:
            dict: Extended properties

        Example:
            ext_props = await user.get_ext_props()
            fresh_props = await user.get_ext_props(use_cache=False)  # Read from storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if not use_cache:
            # Direct storage operation: cache left untouched
            return await self._storage.get_ext_props()

        # Auto-load cache if needed
        if self._cached is None:
            await self._load()

        return self._cached[PropertyType.EXTENDED]["values"].copy()

    async def store(self):
        """
        Persist cached changes to storage.

        Collects all created/updated/deleted properties and persists them.

        Example:
            await user.set("name", "John")
            await user.set("age", 30)
            await user.store()  # Batch persist both changes
        """
        if not self._cached:
            return

        inserts, updates, deletes = [], [], []

        # Collect inserts
        for prop in self._cached[PropertyType.DEFAULT]["created"]:
            value = self._cached[PropertyType.DEFAULT]["values"][prop]
            inserts.append(SubjectProperty(prop, value))
        for prop in self._cached[PropertyType.EXTENDED]["created"]:
            value = self._cached[PropertyType.EXTENDED]["values"][prop]
            inserts.append(SubjectExtProperty(prop, value))

        # Collect updates
        for prop in self._cached[PropertyType.DEFAULT]["updated"]:
            value = self._cached[PropertyType.DEFAULT]["values"][prop]
            updates.append(SubjectProperty(prop, value))
        for prop in self._cached[PropertyType.EXTENDED]["updated"]:
            value = self._cached[PropertyType.EXTENDED]["values"][prop]
            updates.append(SubjectExtProperty(prop, value))

        # Collect deletes
        for prop in self._cached[PropertyType.DEFAULT]["deleted"]:
            deletes.append(SubjectProperty(prop))
        for prop in self._cached[PropertyType.EXTENDED]["deleted"]:
            deletes.append(SubjectExtProperty(prop))

        # Persist to storage
        await self._storage.store(inserts=inserts, updates=updates, deletes=deletes)

        # Clear cache after successful persist
        self._cached = None

    async def flush(self):
        """
        Delete entire subject from storage.

        Emits property-deleted events for all properties, then subject-deleted event.

        Returns:
            self (for chaining)

        Example:
            await user.flush()
        """
        # Collect snapshot before deletion
        props = {}
        ext_props = {}

        if self._cached:
            props = self._cached[PropertyType.DEFAULT]["values"].copy()
            ext_props = self._cached[PropertyType.EXTENDED]["values"].copy()
        else:
            # Load to get current state
            await self._load()
            props = self._cached[PropertyType.DEFAULT]["values"].copy()
            ext_props = self._cached[PropertyType.EXTENDED]["values"].copy()

        # Emit subject-property-deleted for each default property
        for prop_name, prop_value in props.items():
            payload = {
                PayloadConst.PROPERTY_NAME: prop_name,
                PayloadConst.OLD_VALUE: prop_value
            }
            await self._event_bus.emit("subject-property-deleted", self, payload)

        # Emit subject-property-deleted for each extended property
        for prop_name, prop_value in ext_props.items():
            payload = {
                PayloadConst.PROPERTY_NAME: prop_name,
                PayloadConst.OLD_VALUE: prop_value
            }
            await self._event_bus.emit("subject-property-deleted", self, payload)

        # Delete from storage
        await self._storage.flush()

        # Clear cache
        self._cached = None

        # Emit subject-deleted event with snapshot
        snapshot = {
            "props": props,
            "ext_props": ext_props,
        }
        await self._event_bus.emit("subject-deleted", self, snapshot)

        return self

    async def dict(self, use_cache=None):
        """
        Get dict representation of subject.

        Args:
            use_cache: If True, read from the cache; if False, read from storage
                       without creating or touching the cache; if None, use the
                       default from the constructor (default: None)

        Returns:
            dict: Subject properties as dict

        Example:
            data = await user.dict()
            # {"name": "user-123", "email": "...", "ext": {"tenant_id": "..."}}
            fresh_data = await user.dict(use_cache=False)  # Read from storage
        """
        # Determine cache usage
        if use_cache is None:
            use_cache = self._use_cache

        if not use_cache:
            # Direct storage operation: cache left untouched
            props, ext_props = await self._storage.load()
            obj = {"name": self.name}
            obj.update(props)
            obj["ext"] = dict(ext_props)
            return obj

        # Auto-load cache if needed
        if self._cached is None:
            await self._load()

        obj = {"name": self.name}

        # Add default properties
        for prop, value in self._cached[PropertyType.DEFAULT]["values"].items():
            obj[prop] = value

        # Add extended properties under "ext" key
        obj["ext"] = {}
        for prop, value in self._cached[PropertyType.EXTENDED]["values"].items():
            obj["ext"][prop] = value

        return obj
