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
Event context for modern handlers.

Provides a clean API for accessing event data and emitting new events,
while maintaining full compatibility with existing Subject and EventRouter.
"""

from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class EventContext:
    """
    Context object passed to modern event handlers.

    Provides access to event data and utilities for emitting events.
    Wraps existing krules infrastructure for full compatibility.

    Attributes:
        event_type: Type of the event (e.g., "user.login")
        subject: The subject instance (existing Subject class)
        payload: Event payload dictionary
        old_value: Previous value (for property change events)
        new_value: New value (for property change events)
        property_name: Property name (for property change events)

    Example:
        @on("user.login")
        async def handle_login(ctx: EventContext):
            user = ctx.subject
            user.set("last_login", datetime.now())
            await ctx.emit("user.logged-in", {"user_id": user.name})
    """

    event_type: str
    subject: Any  # krules_core.subject.storaged_subject.Subject
    payload: dict
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    property_name: Optional[str] = None
    _metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        """Extract property change metadata from payload if present"""
        from krules_core.subject import PayloadConst

        if PayloadConst.PROPERTY_NAME in self.payload:
            self.property_name = self.payload[PayloadConst.PROPERTY_NAME]
            self.old_value = self.payload.get(PayloadConst.OLD_VALUE)
            self.new_value = self.payload.get(PayloadConst.VALUE)

    async def emit(
        self,
        event_type: str,
        payload: Optional[dict] = None,
        subject: Optional[Any] = None,
        dispatch_policy: Optional[str] = None
    ):
        """
        Emit a new event using the existing event router.

        Args:
            event_type: Type of event to emit
            payload: Event payload (defaults to empty dict)
            subject: Subject for the event (defaults to current subject)
            dispatch_policy: Routing policy (uses router default if None)

        Example:
            await ctx.emit("user.updated", {"field": "email"})
        """
        from krules_core.providers import event_router_factory
        from krules_core.route.router import DispatchPolicyConst

        if payload is None:
            payload = {}
        if subject is None:
            subject = self.subject
        if dispatch_policy is None:
            dispatch_policy = DispatchPolicyConst.DEFAULT

        # Use existing event router for full compatibility
        event_router_factory().route(
            event_type,
            subject,
            payload,
            dispatch_policy=dispatch_policy
        )

    def get_payload(self, key: str, default: Any = None) -> Any:
        """Get value from payload with optional default"""
        return self.payload.get(key, default)

    def set_payload(self, key: str, value: Any):
        """Set value in payload"""
        self.payload[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get custom metadata"""
        return self._metadata.get(key, default)

    def set_metadata(self, key: str, value: Any):
        """Set custom metadata (for handler communication)"""
        self._metadata[key] = value