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

A complete rewrite focusing on simplicity, type safety, and async-first design.

Key features:
- Decorator-based event handlers (@on, @when)
- Dynamic subject system with persistent state
- Async/await native support
- Optional type hints for IDE support
- Multiple storage backends (Redis, SQLite, etc.)

Quick Start:
    from krules_core import on, when, subject_factory

    # Define event handlers
    @on("user.login")
    @when(lambda ctx: ctx.subject.get("status") == "active")
    async def handle_login(ctx):
        user = ctx.subject
        user.set("last_login", datetime.now())
        user.set("login_count", lambda c: c + 1)
        await ctx.emit("user.logged-in")

    # React to property changes
    @on("subject-property-changed")
    @when(lambda ctx: ctx.property_name == "temperature")
    @when(lambda ctx: ctx.new_value > 80)
    async def on_overheat(ctx):
        await ctx.emit("alert.overheat", {
            "device": ctx.subject.name,
            "temp": ctx.new_value
        })

    # Use subjects
    user = subject_factory("user-123")
    user.set("status", "active")
    user.set("email", "user@example.com")

    # Emit events
    from krules_core.handlers import emit
    await emit("user.login", user, {"ip": "1.2.3.4"})

Migration from 1.x:
    See MIGRATION.md for complete migration guide from rule-based system.
"""

# Core event system
from .event_bus import EventBus, EventContext, get_event_bus, set_event_bus, reset_event_bus
from .handlers import on, when, middleware, emit

# Subject system
from .subject.storaged_subject import Subject
from .subject import PayloadConst, PropertyType, SubjectProperty, SubjectExtProperty

# Providers
from .providers import subject_factory, subject_storage_factory, configs_factory

# Legacy compatibility (deprecated, will be removed)
class RuleConst:
    """Deprecated - only for backward compatibility during migration"""
    PAYLOAD_DIFFS = "payload_diffs"
    # Add other constants if needed during migration

# Container
from .container import KRulesContainer

# Version
__version__ = "2.0.0"

__all__ = [
    # Event handling
    "on",
    "when",
    "middleware",
    "emit",
    "EventContext",
    "EventBus",
    "get_event_bus",
    "set_event_bus",
    "reset_event_bus",
    # Subjects
    "Subject",
    "subject_factory",
    "PayloadConst",
    "PropertyType",
    "SubjectProperty",
    "SubjectExtProperty",
    # Storage
    "subject_storage_factory",
    # Config
    "configs_factory",
    # Container
    "KRulesContainer",
]