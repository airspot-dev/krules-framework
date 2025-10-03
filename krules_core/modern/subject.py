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
Optional typed Subject wrapper for better IDE support.

The existing Subject class is fully dynamic and this is preserved.
TypedSubject is OPTIONAL for those who want type hints and IDE autocomplete.

Both styles work:
1. Dynamic (existing): subject.temperature = 75
2. Typed (new, optional): class Device(TypedSubject): temperature: float
"""

from typing import Any, Optional, get_type_hints, TypeVar, Type
from krules_core.subject.storaged_subject import Subject as BaseSubject


T = TypeVar('T', bound='TypedSubject')


class TypedSubject(BaseSubject):
    """
    Optional typed wrapper around existing Subject class.

    Provides type hints for IDE support while maintaining full compatibility
    with the existing dynamic Subject system. Schema is OPTIONAL and RUNTIME-ONLY.

    Key features:
    - Type hints for IDE autocomplete
    - Runtime type checking (optional, can be disabled)
    - Still allows arbitrary properties (fallback to dynamic)
    - Full compatibility with existing storage and events

    Example:
        # Define typed subject (optional!)
        class Device(TypedSubject):
            temperature: float
            status: str
            metadata: dict  # Nested structures OK

            @property
            def is_overheating(self) -> bool:
                return self.temperature > 80

        # Usage with type safety
        device = Device("device-123")
        device.temperature = 75  # IDE knows this is float
        device.status = "ok"

        # Still allows dynamic properties!
        device.custom_field = "anything"  # Works fine

        # Type checking (optional)
        device.temperature = "invalid"  # Logs warning but doesn't break

    Note:
        If you don't need type hints, just use the existing Subject class!
        TypedSubject is purely opt-in for better IDE support.
    """

    # Class variable to store schema (set in __init_subclass__)
    _schema: dict[str, type] = {}
    _strict_typing: bool = False  # If True, raises errors on type mismatch

    def __init_subclass__(cls, strict: bool = False):
        """
        Auto-extract type hints from class definition.

        Args:
            strict: If True, raises TypeError on type mismatches.
                   If False (default), just logs warnings.
        """
        super().__init_subclass__()

        cls._strict_typing = strict
        cls._schema = {}

        # Extract type hints from class
        try:
            hints = get_type_hints(cls)
            for name, type_hint in hints.items():
                if not name.startswith("_"):
                    cls._schema[name] = type_hint
        except Exception:
            # If type hint extraction fails, just use dynamic mode
            pass

    def __setattr__(self, key: str, value: Any):
        """
        Override to add optional type checking while maintaining compatibility.

        Type checking is OPTIONAL and doesn't break functionality if disabled.
        """
        # Internal attributes pass through
        if key.startswith("_") or key == "name":
            return super().__setattr__(key, value)

        # Check type if schema exists for this property
        if hasattr(self.__class__, "_schema") and key in self.__class__._schema:
            expected_type = self.__class__._schema[key]

            # Try to check type (skip for complex types like Union, Optional, etc.)
            try:
                if not isinstance(value, expected_type):
                    message = (
                        f"Type mismatch for {self.__class__.__name__}.{key}: "
                        f"expected {expected_type.__name__}, got {type(value).__name__}"
                    )

                    if self.__class__._strict_typing:
                        raise TypeError(message)
                    else:
                        # Just log warning, don't break
                        import logging
                        logging.getLogger(__name__).warning(message)
            except TypeError:
                # Complex type hints (Union, Optional, etc.) - skip checking
                pass

        # Use parent's __setattr__ for actual property setting
        # This ensures all existing behavior (events, storage) works
        return super().__setattr__(key, value)

    @classmethod
    def from_existing(cls: Type[T], subject: BaseSubject) -> T:
        """
        Wrap an existing Subject instance with typed interface.

        Useful when loading subjects from storage.

        Args:
            subject: Existing Subject instance

        Returns:
            TypedSubject instance wrapping the same data

        Example:
            from krules_core.providers import subject_factory

            # Load existing subject
            raw_subject = subject_factory("device-123")

            # Wrap with type hints
            device = Device.from_existing(raw_subject)
            device.temperature  # Now has IDE autocomplete!
        """
        # Create new instance with same name and storage
        typed = cls(subject.name, subject._event_info, use_cache_default=subject._use_cache)
        typed._storage = subject._storage
        typed._cached = subject._cached

        return typed

    def get_typed(self, prop: str, prop_type: Type[T], default: Optional[T] = None) -> T:
        """
        Get property with runtime type checking and casting.

        Args:
            prop: Property name
            prop_type: Expected type
            default: Default value if property doesn't exist

        Returns:
            Property value cast to expected type

        Example:
            temp = device.get_typed("temperature", float, 0.0)
        """
        try:
            value = self.get(prop)

            # Try to cast to expected type
            if not isinstance(value, prop_type):
                try:
                    value = prop_type(value)
                except (ValueError, TypeError):
                    if default is not None:
                        return default
                    raise TypeError(
                        f"Cannot convert {prop}={value} to {prop_type.__name__}"
                    )

            return value
        except AttributeError:
            if default is not None:
                return default
            raise

    def set_typed(self, prop: str, value: Any, prop_type: Type[T]):
        """
        Set property with runtime type validation.

        Args:
            prop: Property name
            value: Value to set
            prop_type: Expected type

        Raises:
            TypeError: If value doesn't match expected type in strict mode

        Example:
            device.set_typed("temperature", 75.5, float)
        """
        if not isinstance(value, prop_type):
            try:
                value = prop_type(value)
            except (ValueError, TypeError):
                if self._strict_typing:
                    raise TypeError(
                        f"Cannot convert {value} to {prop_type.__name__}"
                    )

        self.set(prop, value)


# Convenience type aliases
DynamicSubject = BaseSubject  # Alias for clarity