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
Tests for CloudEvents HTTP receiver endpoint.
"""

import pytest
from fastapi.testclient import TestClient


class TestCloudEventsEndpoint:
    """Test suite for CloudEvents HTTP receiver"""

    def test_cloudevents_endpoint_exists(self, krules_app):
        """POST / endpoint should exist."""
        client = TestClient(krules_app)
        # Sending invalid data should return 422 (validation error), not 404
        response = client.post("/", json={})
        assert response.status_code != 404

    def test_cloudevents_endpoint_custom_path(self, krules_app_custom_path):
        """POST /events endpoint should exist with custom path."""
        client = TestClient(krules_app_custom_path)
        response = client.post("/events", json={})
        assert response.status_code != 404

    def test_receive_valid_cloudevent(self, krules_app):
        """Endpoint should accept valid CloudEvent and emit on EventBus."""
        client = TestClient(krules_app)

        # Track emitted events
        emitted_events = []

        # Get handlers from container
        on, _, _, _ = krules_app._krules.handlers()

        @on("test.event")
        async def capture_event(ctx):
            emitted_events.append({
                "type": ctx.event_type,
                "subject": ctx.subject,
                "payload": ctx.payload
            })

        # Send CloudEvent
        response = client.post("/", json={
            "specversion": "1.0",
            "type": "test.event",
            "source": "test-suite",
            "id": "test-123",
            "subject": "test-subject",
            "data": {"message": "hello"}
        })

        assert response.status_code == 200
        assert response.json() == {"status": "accepted"}

        # Verify event was emitted
        assert len(emitted_events) == 1
        assert emitted_events[0]["type"] == "test.event"

        # Subject should be a Subject instance, not a string
        from krules_core.subject.storaged_subject import Subject
        assert isinstance(emitted_events[0]["subject"], Subject)
        assert emitted_events[0]["subject"].name == "test-subject"

        assert emitted_events[0]["payload"] == {"message": "hello"}

    def test_receive_cloudevent_without_subject(self, krules_app):
        """Endpoint should reject CloudEvents without subject field (malformed)."""
        client = TestClient(krules_app)

        response = client.post("/", json={
            "specversion": "1.0",
            "type": "test.event",
            "source": "test-suite",
            "id": "test-456",
            "data": {"foo": "bar"}
        })

        # Subject is required for KRules - should return 422
        assert response.status_code == 422
        assert "subject" in response.json()["detail"].lower()

    def test_receive_cloudevent_without_data(self, krules_app):
        """Endpoint should handle CloudEvents without data field."""
        client = TestClient(krules_app)

        emitted_events = []

        on, _, _, _ = krules_app._krules.handlers()

        @on("test.event")
        async def capture_event(ctx):
            emitted_events.append({"payload": ctx.payload})

        response = client.post("/", json={
            "specversion": "1.0",
            "type": "test.event",
            "source": "test-suite",
            "id": "test-789",
            "subject": "test-subject-data"  # Subject is required
        })

        assert response.status_code == 200
        assert emitted_events[0]["payload"] == {}  # Default to empty dict

    def test_receive_cloudevent_with_empty_subject(self, krules_app):
        """Endpoint should reject CloudEvents with empty subject string."""
        client = TestClient(krules_app)

        response = client.post("/", json={
            "specversion": "1.0",
            "type": "test.event",
            "source": "test-suite",
            "id": "test-empty",
            "subject": ""  # Empty string should be rejected
        })

        # Empty subject is invalid for KRules
        assert response.status_code == 422
        assert "subject" in response.json()["detail"].lower()

    def test_invalid_cloudevent_missing_required_fields(self, krules_app):
        """Endpoint should reject CloudEvents missing required fields."""
        client = TestClient(krules_app)

        # Missing 'type' and 'source'
        response = client.post("/", json={
            "specversion": "1.0",
            "id": "test-999"
        })

        assert response.status_code == 422  # Validation error
