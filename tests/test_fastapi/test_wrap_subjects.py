import logging
from io import StringIO

import pytest
from fastapi.testclient import TestClient

from krules_fastapi_env import KrulesApp, ctx_subjects
from krules_core.providers import subject_factory

@pytest.fixture(scope="session")
def app():
    app = KrulesApp(wrap_subjects=True)  # Create an app with wrapping enabled

    @app.get("/test-endpoint")  # Now within the app's scope
    def test_endpoint():
        subject = subject_factory("hello")  # Use subject_factory
        app.logger.debug(f"Subject created: {subject}")  # Log the created subject
        return {"message": "Test endpoint called"}

    return app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)


def test_subject_wrapping(client, app):
    log_capture_string = StringIO()
    ch = logging.StreamHandler(log_capture_string)
    app.logger.addHandler(ch)
    app.logger.setLevel(logging.DEBUG)

    response = client.get("/test-endpoint")  # Make a request to the correct endpoint
    assert response.status_code == 200
    assert response.json() == {"message": "Test endpoint called"}

    log_contents = log_capture_string.getvalue()
    assert "wrapped:" in log_contents





