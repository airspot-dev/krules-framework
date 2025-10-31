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
Tests for CloudEventsDispatcher (HTTP publisher).
"""

import pytest
import httpx
from unittest.mock import Mock, patch, ANY
from krules_cloudevents import CloudEventsDispatcher
from krules_core.subject import PayloadConst


class TestCloudEventsDispatcher:
    """Tests for CloudEventsDispatcher HTTP publisher."""

    def test_dispatcher_requires_container(self):
        """Test that dispatcher requires krules_container."""
        with pytest.raises(ValueError, match="krules_container is required"):
            CloudEventsDispatcher(
                dispatch_url="https://api.example.com/events",
                source="test-service",
                krules_container=None,
            )

    def test_dispatcher_initialization(self, container, mock_http_url):
        """Test successful dispatcher initialization."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        assert dispatcher._dispatch_url == mock_http_url
        assert dispatcher._source == "test-service"
        assert dispatcher._krules == container
        assert dispatcher.default_dispatch_policy == "direct"

    def test_dispatch_with_string_subject(self, container, mock_http_url):
        """Test dispatching with string subject (auto-resolves via container)."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            event_id = dispatcher.dispatch(
                event_type="test.event",
                subject="test-subject-123",
                payload={"data": "test"},
            )

            assert isinstance(event_id, str)
            mock_post.assert_called_once()

            # Verify CloudEvents headers
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert "ce-id" in headers
            assert headers["ce-type"] == "test.event"
            assert headers["ce-source"] == "test-service"
            assert headers["ce-subject"] == "test-subject-123"
            assert "ce-time" in headers

    def test_dispatch_with_subject_instance(self, container, mock_http_url):
        """Test dispatching with Subject instance."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("order-456")
        subject.set("status", "pending")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            event_id = dispatcher.dispatch(
                event_type="order.created",
                subject=subject,
                payload={"amount": 100.0},
            )

            assert isinstance(event_id, str)

            # Verify headers
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-type"] == "order.created"
            assert headers["ce-subject"] == "order-456"

    def test_dispatch_preserves_originid(self, container, mock_http_url):
        """Test that originid is preserved from event_info."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        # Create subject with event_info containing originid
        subject = container.subject(
            "test-subject",
            event_info={"originid": "original-event-id-123"}
        )

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
            )

            # Verify originid header
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-originid"] == "original-event-id-123"

    def test_dispatch_creates_originid_if_missing(self, container, mock_http_url):
        """Test that originid is set to event ID if not in event_info."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            event_id = dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
            )

            # Verify originid equals event_id
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-originid"] == event_id

    def test_dispatch_with_extended_properties(self, container, mock_http_url):
        """Test that extended properties from subject are included."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")
        subject.set_ext("custom_field", "custom_value")
        subject.set_ext("tenant_id", "tenant-123")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
            )

            # Verify extended properties in headers
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-custom_field"] == "custom_value"
            assert headers["ce-tenant_id"] == "tenant-123"

    def test_dispatch_with_property_name_in_payload(self, container, mock_http_url):
        """Test that propertyname is added from payload."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="subject.property-changed",
                subject=subject,
                payload={
                    PayloadConst.PROPERTY_NAME: "status",
                    "value": "active",
                },
            )

            # Verify propertyname header
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-propertyname"] == "status"

    def test_dispatch_with_callable_url(self, container):
        """Test dynamic dispatch URL (callable)."""
        def get_url(subject, event_type):
            return f"https://api.example.com/{event_type}/process"

        dispatcher = CloudEventsDispatcher(
            dispatch_url=get_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="order.created",
                subject=subject,
                payload={"data": "test"},
            )

            # Verify URL was generated dynamically
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://api.example.com/order.created/process"

    def test_dispatch_url_override_in_kwargs(self, container, mock_http_url):
        """Test overriding dispatch_url via kwargs."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")
        override_url = "https://override.example.com/events"

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
                dispatch_url=override_url,
            )

            # Verify override URL was used
            call_args = mock_post.call_args
            assert call_args[0][0] == override_url

    def test_dispatch_http_error(self, container, mock_http_url):
        """Test handling of HTTP errors."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            # Simulate 500 error
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_post.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "500 Server Error", request=Mock(), response=mock_response
            )

            with pytest.raises(httpx.HTTPStatusError):
                dispatcher.dispatch(
                    event_type="test.event",
                    subject=subject,
                    payload={"data": "test"},
                )

    def test_dispatch_test_mode(self, container, mock_http_url):
        """Test dispatcher in test mode (returns extended info)."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
            test=True,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_post.return_value = mock_response

            result = dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
            )

            # Verify test mode returns tuple
            assert isinstance(result, tuple)
            event_id, status, headers = result
            assert isinstance(event_id, str)
            assert status == 201
            assert isinstance(headers, dict)

    def test_dispatch_extra_kwargs_as_extensions(self, container, mock_http_url):
        """Test that extra kwargs are added as CloudEvent extensions."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"data": "test"},
                custom_ext="value1",
                another_ext="value2",
            )

            # Verify extra kwargs in headers
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            assert headers["ce-custom_ext"] == "value1"
            assert headers["ce-another_ext"] == "value2"

    def test_dispatch_json_serialization(self, container, mock_http_url):
        """Test JSON serialization of payload."""
        dispatcher = CloudEventsDispatcher(
            dispatch_url=mock_http_url,
            source="test-service",
            krules_container=container,
        )

        subject = container.subject("test-subject")

        with patch("httpx.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            dispatcher.dispatch(
                event_type="test.event",
                subject=subject,
                payload={"nested": {"data": "value"}, "number": 42},
            )

            # Verify content type and body
            call_kwargs = mock_post.call_args.kwargs
            headers = call_kwargs["headers"]
            body = call_kwargs["content"]

            assert headers["content-type"] == "application/json"
            assert '"nested"' in body
            assert '"number": 42' in body
