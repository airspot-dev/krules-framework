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
Tests for KRules event type constants
"""

import pytest
from krules_core.container import KRulesContainer
from krules_core import EventContext
from krules_core import event_types


# Global container and decorators for the test module
container = None
on = None
when = None
middleware = None
emit = None


@pytest.fixture(autouse=True)
def setup():
    """Create fresh container before each test"""
    global container, on, when, middleware, emit

    # Create new container for each test (isolation)
    container = KRulesContainer()

    # Get handlers from container
    on, when, middleware, emit = container.handlers()

    yield

    # Cleanup
    container = None


class TestEventTypeConstants:
    """Test suite for event type constants"""

    def test_event_type_constants_exist(self):
        """Event type constants should be defined correctly"""
        # Constants should exist and be strings
        assert hasattr(event_types, "SUBJECT_PROPERTY_CHANGED")
        assert hasattr(event_types, "SUBJECT_PROPERTY_DELETED")
        assert hasattr(event_types, "SUBJECT_DELETED")
        assert hasattr(event_types, "SUBJECT_FLUSHED")  # Legacy alias

        assert isinstance(event_types.SUBJECT_PROPERTY_CHANGED, str)
        assert isinstance(event_types.SUBJECT_PROPERTY_DELETED, str)
        assert isinstance(event_types.SUBJECT_DELETED, str)
        assert isinstance(event_types.SUBJECT_FLUSHED, str)

        # Verify actual values
        assert event_types.SUBJECT_PROPERTY_CHANGED == "subject-property-changed"
        assert event_types.SUBJECT_PROPERTY_DELETED == "subject-property-deleted"
        assert event_types.SUBJECT_DELETED == "subject-deleted"

        # Legacy alias SUBJECT_FLUSHED should point to "subject-deleted"
        assert event_types.SUBJECT_FLUSHED == "subject-deleted"

        # Legacy aliases should also exist
        assert hasattr(event_types, "SubjectPropertyChanged")
        assert hasattr(event_types, "SubjectPropertyDeleted")
        assert hasattr(event_types, "SubjectDeleted")
        assert hasattr(event_types, "SubjectFlushed")  # Legacy alias

        # Aliases should equal their corresponding constants
        assert event_types.SubjectPropertyChanged == event_types.SUBJECT_PROPERTY_CHANGED
        assert event_types.SubjectPropertyDeleted == event_types.SUBJECT_PROPERTY_DELETED
        assert event_types.SubjectDeleted == event_types.SUBJECT_DELETED
        assert event_types.SubjectFlushed == event_types.SUBJECT_FLUSHED

    @pytest.mark.asyncio
    async def test_property_changed_event_emitted(self):
        """Subject property changes should emit SUBJECT_PROPERTY_CHANGED events"""
        changes = []

        @on(event_types.SUBJECT_PROPERTY_CHANGED)
        async def handler(ctx: EventContext):
            changes.append({
                "property": ctx.property_name,
                "old": ctx.old_value,
                "new": ctx.new_value,
                "subject_name": ctx.subject.name
            })

        subject = container.subject("device-123")
        subject.set("temperature", 75)
        subject.set("temperature", 85)
        subject.set("status", "ok")

        # Give async events time to process
        import asyncio
        await asyncio.sleep(0.01)

        assert len(changes) == 3

        # First change: temperature set to 75
        assert changes[0]["property"] == "temperature"
        assert changes[0]["old"] is None
        assert changes[0]["new"] == 75
        assert changes[0]["subject_name"] == "device-123"

        # Second change: temperature updated to 85
        assert changes[1]["property"] == "temperature"
        assert changes[1]["old"] == 75
        assert changes[1]["new"] == 85

        # Third change: status set to ok
        assert changes[2]["property"] == "status"
        assert changes[2]["old"] is None
        assert changes[2]["new"] == "ok"

    @pytest.mark.asyncio
    async def test_property_deleted_event_emitted(self):
        """Subject property deletions should emit SUBJECT_PROPERTY_DELETED events with old_value"""
        deletions = []

        @on(event_types.SUBJECT_PROPERTY_DELETED)
        async def handler(ctx: EventContext):
            deletions.append({
                "property": ctx.property_name,
                "old_value": ctx.old_value,
                "subject_name": ctx.subject.name
            })

        subject = container.subject("user-456")
        subject.set("email", "user@example.com")
        subject.set("temp_token", "abc123")

        # Give time for property-changed events to process
        import asyncio
        await asyncio.sleep(0.01)

        # Now delete properties
        subject.delete("temp_token")
        subject.delete("email")

        # Give time for deletion events to process
        await asyncio.sleep(0.01)

        assert len(deletions) == 2

        # First deletion - should include old value
        assert deletions[0]["property"] == "temp_token"
        assert deletions[0]["old_value"] == "abc123"
        assert deletions[0]["subject_name"] == "user-456"

        # Second deletion - should include old value
        assert deletions[1]["property"] == "email"
        assert deletions[1]["old_value"] == "user@example.com"
        assert deletions[1]["subject_name"] == "user-456"

    @pytest.mark.asyncio
    async def test_constants_work_with_decorators(self):
        """Event type constants should work seamlessly with @on decorator"""
        using_constant = []
        using_string = []

        # Handler using constant
        @on(event_types.SUBJECT_PROPERTY_CHANGED)
        async def handler_constant(ctx: EventContext):
            using_constant.append(ctx.event_type)

        # Handler using string directly (should be equivalent)
        @on("subject-property-changed")
        async def handler_string(ctx: EventContext):
            using_string.append(ctx.event_type)

        subject = container.subject("test")
        subject.set("value", 42)

        import asyncio
        await asyncio.sleep(0.01)

        # Both handlers should have been called
        assert len(using_constant) == 1
        assert len(using_string) == 1

        # Both should have received the same event type
        assert using_constant[0] == "subject-property-changed"
        assert using_string[0] == "subject-property-changed"
