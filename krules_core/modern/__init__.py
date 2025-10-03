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
KRules Modern API - Decorator-based event handlers with optional type safety

This module provides a modern, decorator-based API that coexists with the
existing rule-based system. It's 100% backward compatible and optional.

Key features:
- Decorator-based handlers (@on, @when)
- Optional type hints for IDE support
- Fully dynamic subjects (no schema required)
- Async/await native support
- Compatible with existing Subject storage and event routing

Example:
    from krules_core.modern import on, when
    from krules_core.providers import subject_factory

    @on("user.login")
    @when(lambda ctx: ctx.subject.get("status") == "active")
    async def handle_login(ctx):
        user = ctx.subject
        user.set("last_login", datetime.now())
        await ctx.emit("user.logged-in")
"""

from .decorators import on, when, route_event, register_modern_handlers
from .context import EventContext
from .subject import TypedSubject

__all__ = [
    "on",
    "when",
    "route_event",
    "register_modern_handlers",
    "EventContext",
    "TypedSubject",
]