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
Tests for Subject system in KRules 2.0
"""

import pytest
from krules_core import subject_factory, reset_event_bus
from krules_core.providers import subject_storage_factory
from krules_core.subject.empty_storage import EmptySubjectStorage
from dependency_injector import providers


@pytest.fixture(autouse=True)
def setup():
    """Reset before each test"""
    reset_event_bus()
    subject_storage_factory.override(
        providers.Factory(lambda *args, **kwargs: EmptySubjectStorage())
    )
    yield


def test_subject_dynamic_properties():
    """Subject should support dynamic properties"""
    subject = subject_factory("test-subject")

    subject.set("name", "John")
    subject.set("age", 30)
    subject.set("active", True)

    assert subject.get("name") == "John"
    assert subject.get("age") == 30
    assert subject.get("active") == True


def test_subject_lambda_values():
    """Subject.set() should support lambda for computed values"""
    subject = subject_factory("counter")

    subject.set("count", 0)
    subject.set("count", lambda c: c + 1)
    subject.set("count", lambda c: c + 1)
    subject.set("count", lambda c: c + 1)

    assert subject.get("count") == 3


def test_subject_default_values():
    """Subject.get() should support default values"""
    subject = subject_factory("test")

    # Property doesn't exist - should return default
    value = subject.get("missing", default="default-value")
    assert value == "default-value"

    # Property doesn't exist - should raise without default
    with pytest.raises(AttributeError):
        subject.get("missing")


def test_subject_extended_properties():
    """Subject should support extended properties"""
    subject = subject_factory("test")

    subject.set_ext("metadata", {"key": "value"})
    subject.set_ext("tags", ["tag1", "tag2"])

    assert subject.get_ext("metadata") == {"key": "value"}
    assert subject.get_ext("tags") == ["tag1", "tag2"]

    ext_props = subject.get_ext_props()
    assert "metadata" in ext_props
    assert "tags" in ext_props


def test_subject_iteration():
    """Subject should be iterable over property names"""
    subject = subject_factory("test")

    subject.set("prop1", "value1")
    subject.set("prop2", "value2")
    subject.set("prop3", "value3")

    props = list(subject)
    assert len(props) == 3
    assert "prop1" in props
    assert "prop2" in props
    assert "prop3" in props


def test_subject_contains():
    """Subject should support 'in' operator"""
    subject = subject_factory("test")

    subject.set("exists", True)

    assert "exists" in subject
    assert "missing" not in subject


def test_subject_length():
    """Subject should report number of properties"""
    subject = subject_factory("test")

    assert len(subject) == 0

    subject.set("prop1", 1)
    assert len(subject) == 1

    subject.set("prop2", 2)
    subject.set("prop3", 3)
    assert len(subject) == 3


def test_subject_dict_export():
    """Subject.dict() should export all properties"""
    subject = subject_factory("device-123")

    subject.set("temperature", 75)
    subject.set("status", "ok")
    subject.set_ext("metadata", {"location": "room1"})

    data = subject.dict()

    assert data["name"] == "device-123"
    assert data["temperature"] == 75
    assert data["status"] == "ok"
    assert data["ext"]["metadata"] == {"location": "room1"}


def test_subject_muted_properties():
    """Muted properties should not emit change events"""
    subject = subject_factory("test")

    # Normal set emits event
    subject.set("normal", "value")

    # Muted set does not emit event
    subject.set("muted", "value", muted=True)

    # Both should be stored
    assert subject.get("normal") == "value"
    assert subject.get("muted") == "value"


def test_subject_delete():
    """Subject should support property deletion"""
    subject = subject_factory("test")

    subject.set("temp", 75)
    assert "temp" in subject

    subject.delete("temp")
    assert "temp" not in subject

    with pytest.raises(AttributeError):
        subject.get("temp")