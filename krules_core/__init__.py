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
KRules Framework 2.0 - Modern Event-Driven Application Framework

A complete rewrite focusing on dependency injection, type safety, and async-first design.

Key features:
- Container-based dependency injection (KRulesContainer)
- Decorator-based event handlers (@on, @when)
- Dynamic subject system with persistent state
- Async/await native support
- Multiple storage backends (Redis, SQLite, etc.)

Quick Start:
    from krules_core.container import KRulesContainer

    # Create container
    container = KRulesContainer()

    # Get handlers (decorators and emit function) bound to container's event bus
    on, when, middleware, emit = container.handlers()

    # Define event handlers
    @on("user.login")
    @when(lambda ctx: ctx.subject.get("status") == "active")
    async def handle_login(ctx):
        user = ctx.subject
        user.set("last_login", datetime.now())
        user.set("login_count", lambda c: c + 1)
        await emit("user.logged-in", ctx.subject)

    # React to property changes
    @on("subject-property-changed")
    @when(lambda ctx: ctx.property_name == "temperature")
    @when(lambda ctx: ctx.new_value > 80)
    async def on_overheat(ctx):
        await emit("alert.overheat", ctx.subject, {
            "device": ctx.subject.name,
            "temp": ctx.new_value
        })

    # Use subjects
    user = container.subject("user-123")
    user.set("status", "active")
    user.set("email", "user@example.com")

    # Emit events
    await emit("user.login", user, {"ip": "1.2.3.4"})

Migration from 1.x:
    See MIGRATION.md for complete migration guide from rule-based system.
"""

# Core event system
from .event_bus import EventBus, EventContext

# Subject system
from .subject.storaged_subject import Subject
from .subject import PayloadConst, PropertyType, SubjectProperty, SubjectExtProperty

# Container (PRIMARY API)
from .container import KRulesContainer

# Version
__version__ = "2.0.0"

__all__ = [
    # Container (PRIMARY API - use this)
    "KRulesContainer",
    # Event system
    "EventContext",
    "EventBus",
    # Subjects
    "Subject",
    "PayloadConst",
    "PropertyType",
    "SubjectProperty",
    "SubjectExtProperty",
]