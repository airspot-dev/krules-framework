"""
KRules FastAPI Integration

Provides KrulesApp - a FastAPI application pre-configured for KRules integration.

Features:
- Automatic CloudEvents HTTP receiver endpoint (POST /)
- Container-first pattern (receives KRulesContainer as dependency)

Example:
    from dependency_injector import containers, providers
    from krules_core.container import KRulesContainer
    from krules_fastapi_env import KrulesApp

    # Application container with KRules sub-container
    class AppContainer(containers.DeclarativeContainer):
        config = providers.Configuration()
        krules = providers.Container(KRulesContainer, config=config.krules)

    container = AppContainer()

    # KrulesApp with injected krules container
    app = KrulesApp(
        krules_container=container.krules,
        title="My KRules API"
    )

    # Lifespan management is application responsibility
    @app.on_event("startup")
    async def startup():
        container.init_resources()
        from my_app import handlers  # Register event handlers
"""

from fastapi import FastAPI
from cloudevents.pydantic import CloudEvent

from krules_core.container import KRulesContainer


class KrulesApp(FastAPI):
    """
    FastAPI application with KRules integration.

    Provides:
    - CloudEvents HTTP receiver endpoint (POST /)
    - Container-first dependency injection pattern

    Args:
        krules_container: KRulesContainer instance (dependency injected)
        cloudevents_path: Path for CloudEvents receiver endpoint (default: "/")
        *args, **kwargs: Passed to FastAPI.__init__

    Note:
        Subject persistence (.store()) must be called explicitly by the application.
        For automatic persistence, use a custom middleware in your application.
    """

    def __init__(
            self,
            krules_container: KRulesContainer,
            cloudevents_path: str = "/",
            *args, **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self._krules = krules_container

        # Register CloudEvents receiver endpoint
        self._register_cloudevents_endpoint(cloudevents_path)

    def _register_cloudevents_endpoint(self, path: str):
        """
        Register CloudEvents HTTP receiver endpoint.

        Creates a POST endpoint that receives CloudEvents via HTTP and emits
        them on the local EventBus. This is the HTTP equivalent of PubSub subscriber.

        Args:
            path: Endpoint path (e.g., "/" or "/events")
        """
        @self.post(path)
        async def receive_cloudevent(event: CloudEvent):
            """
            Receive CloudEvent via HTTP POST and emit on EventBus.

            Accepts CloudEvents in both binary and structured format.
            Extracted event is emitted on the local EventBus, triggering
            registered @on handlers.

            Request Body:
                CloudEvent (JSON) with required fields:
                - type: Event type (e.g., "order.created")
                - source: Event source identifier
                - id: Event ID (auto-generated if not provided)
                - subject: Subject name (REQUIRED for KRules)
                Optional fields:
                - data: Event payload (JSON)

            Returns:
                {"status": "accepted"}

            Raises:
                422: If subject is missing or empty (malformed request)
            """
            from fastapi import HTTPException

            # Validate subject is present (required for KRules)
            if not event.subject:
                raise HTTPException(
                    status_code=422,
                    detail="CloudEvent 'subject' field is required for KRules events"
                )

            # Create Subject instance (like PubSub subscriber does)
            subject = self._krules.subject(event.subject)

            # Emit event on EventBus with Subject instance
            await self._krules.event_bus().emit(
                event_type=event.type,
                subject=subject,
                payload=event.data or {}
            )

            return {"status": "accepted"}
