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
Tests for Subject.flush() - subject deletion
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


class TestSubjectFlush:
    """Test suite for Subject.flush() (subject deletion)"""

    @pytest.mark.asyncio
    async def test_flush_emits_property_deleted_events(self):
        """flush() should emit subject-property-deleted for each property"""
        property_deletions = []

        @on(event_types.SUBJECT_PROPERTY_DELETED)
        async def handler(ctx: EventContext):
            property_deletions.append({
                "property": ctx.property_name,
                "old_value": ctx.old_value,
                "subject_name": ctx.subject.name
            })

        subject = container.subject("user-123")
        await subject.set("email", "user@example.com")
        await subject.set("age", 30)
        await subject.set("status", "active")

        # Flush (delete) the subject
        await subject.flush()

        # Give async events time to process
        import asyncio
        await asyncio.sleep(0.01)

        # Should have emitted property-deleted for each property
        assert len(property_deletions) == 3

        # Check all properties were included
        props_deleted = {p["property"] for p in property_deletions}
        assert "email" in props_deleted
        assert "age" in props_deleted
        assert "status" in props_deleted

        # Check old values are correct
        for deletion in property_deletions:
            if deletion["property"] == "email":
                assert deletion["old_value"] == "user@example.com"
            elif deletion["property"] == "age":
                assert deletion["old_value"] == 30
            elif deletion["property"] == "status":
                assert deletion["old_value"] == "active"

    @pytest.mark.asyncio
    async def test_flush_emits_subject_deleted_event(self):
        """flush() should emit subject-deleted with final snapshot"""
        subject_deletions = []

        @on(event_types.SUBJECT_DELETED)
        async def handler(ctx: EventContext):
            subject_deletions.append({
                "subject_name": ctx.subject.name,
                "props": ctx.payload.get("props", {}),
                "ext_props": ctx.payload.get("ext_props", {})
            })

        subject = container.subject("device-456")
        await subject.set("temperature", 75.5)
        await subject.set("status", "online")

        # Flush (delete) the subject
        await subject.flush()

        # Give async events time to process
        import asyncio
        await asyncio.sleep(0.01)

        # Should have emitted subject-deleted
        assert len(subject_deletions) == 1

        deletion = subject_deletions[0]
        assert deletion["subject_name"] == "device-456"
        assert deletion["props"]["temperature"] == 75.5
        assert deletion["props"]["status"] == "online"

    @pytest.mark.asyncio
    async def test_flush_with_extended_properties(self):
        """flush() should handle extended properties correctly"""
        property_deletions = []

        @on(event_types.SUBJECT_PROPERTY_DELETED)
        async def handler(ctx: EventContext):
            property_deletions.append({
                "property": ctx.property_name,
                "old_value": ctx.old_value
            })

        subject = container.subject("test-subject")
        await subject.set("normal_prop", "value1")
        await subject.set_ext("extended_prop", "value2")

        # Flush (delete) the subject
        await subject.flush()

        # Give async events time to process
        import asyncio
        await asyncio.sleep(0.01)

        # Should have emitted property-deleted for both types
        assert len(property_deletions) == 2

        props = {p["property"]: p["old_value"] for p in property_deletions}
        assert props["normal_prop"] == "value1"
        assert props["extended_prop"] == "value2"

    @pytest.mark.asyncio
    async def test_flush_resets_cache(self):
        """flush() should reset the cache after deletion"""
        subject = container.subject("cache-test")
        await subject.set("prop1", "value1")

        # Cache should be populated
        assert subject._cached is not None

        # Flush (delete) the subject
        await subject.flush()

        # Cache should be reset
        assert subject._cached is None

    @pytest.mark.asyncio
    async def test_flush_with_empty_subject(self):
        """flush() should work with subject that has no properties"""
        subject_deletions = []

        @on(event_types.SUBJECT_DELETED)
        async def handler(ctx: EventContext):
            subject_deletions.append(ctx.payload)

        subject = container.subject("empty-subject")

        # Flush empty subject
        await subject.flush()

        # Give async events time to process
        import asyncio
        await asyncio.sleep(0.01)

        # Should still emit subject-deleted with empty snapshot
        assert len(subject_deletions) == 1
        assert subject_deletions[0]["props"] == {}
        assert subject_deletions[0]["ext_props"] == {}

    @pytest.mark.asyncio
    async def test_flush_returns_self(self):
        """flush() should return AwaitableResult(self)"""
        subject = container.subject("return-test")
        await subject.set("test", "value")

        result = await subject.flush()

        # Should return the subject itself
        assert result is subject

    @pytest.mark.asyncio
    async def test_subject_deleted_constant_works(self):
        """SUBJECT_DELETED constant should work with decorator"""
        deleted_subjects = []

        @on(event_types.SUBJECT_DELETED)
        async def handler(ctx: EventContext):
            deleted_subjects.append(ctx.subject.name)

        subject = container.subject("constant-test")
        await subject.set("prop", "value")

        await subject.flush()

        import asyncio
        await asyncio.sleep(0.01)

        assert len(deleted_subjects) == 1
        assert deleted_subjects[0] == "constant-test"

    @pytest.mark.asyncio
    async def test_legacy_subject_flushed_alias(self):
        """SUBJECT_FLUSHED (legacy alias) should still work"""
        flushed_subjects = []

        @on(event_types.SUBJECT_FLUSHED)  # Legacy alias
        async def handler(ctx: EventContext):
            flushed_subjects.append(ctx.subject.name)

        subject = container.subject("legacy-test")
        await subject.set("prop", "value")

        await subject.flush()

        import asyncio
        await asyncio.sleep(0.01)

        # Should work because SUBJECT_FLUSHED = "subject-deleted"
        assert len(flushed_subjects) == 1
        assert flushed_subjects[0] == "legacy-test"
