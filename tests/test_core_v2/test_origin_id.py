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
Tests for transparent origin_id propagation across event chains.

Focused on the two guarantees that regress silently: concurrent-chain
isolation and implicit inheritance across the async chain (including the
implicit events produced by Subject.set()).
"""

import asyncio
import inspect

import pytest

from krules_core.container import KRulesContainer
from krules_core import EventContext
from krules_core.subject.storaged_subject import Subject
from krules_core.origin import origin_id_scope, get_origin_id


container = None
on = None
when = None
middleware = None
emit = None


@pytest.fixture(autouse=True)
def setup():
    """Create a fresh container before each test (isolation)."""
    global container, on, when, middleware, emit
    container = KRulesContainer()
    on, when, middleware, emit = container.handlers()
    yield
    container = None


@pytest.mark.asyncio
async def test_origin_id_populated_for_every_event():
    """Every emitted event exposes a non-empty origin_id on its context."""
    captured = []

    @on("test.event")
    async def handler(ctx: EventContext):
        captured.append(ctx.origin_id)

    await emit("test.event", container.subject("s"))

    assert len(captured) == 1
    assert captured[0]  # non-empty auto-generated root


@pytest.mark.asyncio
async def test_explicit_origin_id_scope_is_honored():
    """An entry point can pin a specific origin_id via origin_id_scope()."""
    captured = []

    @on("test.event")
    async def handler(ctx: EventContext):
        captured.append(ctx.origin_id)

    with origin_id_scope("fixed-root-123"):
        await emit("test.event", container.subject("s"))

    assert captured == ["fixed-root-123"]


@pytest.mark.asyncio
async def test_inheritance_across_explicit_ctx_emit():
    """An event emitted from within a handler inherits the chain's origin_id."""
    seen = {}

    @on("chain.start")
    async def start(ctx: EventContext):
        seen["start"] = ctx.origin_id
        await ctx.emit("chain.next")

    @on("chain.next")
    async def nxt(ctx: EventContext):
        seen["next"] = ctx.origin_id

    with origin_id_scope("root-abc"):
        await emit("chain.start", container.subject("s"))

    assert seen["start"] == "root-abc"
    assert seen["next"] == "root-abc"


@pytest.mark.asyncio
async def test_inheritance_across_implicit_subject_set_event():
    """
    The implicit subject-property-changed event produced by Subject.set()
    inside a handler inherits the same origin_id — no manual threading.
    """
    seen = {}

    @on("chain.start")
    async def start(ctx: EventContext):
        seen["start"] = ctx.origin_id
        # Implicit event: Subject.set() emits "subject-property-changed"
        await ctx.subject.set("temperature", 42)

    @on("subject-property-changed")
    async def on_changed(ctx: EventContext):
        seen["implicit"] = ctx.origin_id

    with origin_id_scope("root-xyz"):
        await emit("chain.start", container.subject("device-1"))

    assert seen["start"] == "root-xyz"
    assert seen["implicit"] == "root-xyz"


@pytest.mark.asyncio
async def test_concurrent_chains_are_isolated():
    """
    Two chains running concurrently carry independent origin_id values with no
    leakage, even when their handlers interleave.
    """
    captured = {}

    @on("test.concurrent")
    async def handler(ctx: EventContext):
        # Force interleaving between the two concurrent tasks
        await asyncio.sleep(0)
        captured[ctx.payload["label"]] = ctx.origin_id
        await asyncio.sleep(0)

    async def run_chain(label, oid):
        with origin_id_scope(oid):
            await emit("test.concurrent", container.subject(label), {"label": label})

    await asyncio.gather(
        run_chain("A", "origin-A"),
        run_chain("B", "origin-B"),
    )

    assert captured == {"A": "origin-A", "B": "origin-B"}


@pytest.mark.asyncio
async def test_sequential_top_level_emits_get_independent_roots():
    """
    Two bare top-level emits (no explicit scope) are distinct chains: each gets
    its own auto-generated root — the first does not leak into the second.
    """
    captured = []

    @on("test.event")
    async def handler(ctx: EventContext):
        captured.append(ctx.origin_id)

    await emit("test.event", container.subject("s"))
    await emit("test.event", container.subject("s"))

    assert len(captured) == 2
    assert captured[0] and captured[1]
    assert captured[0] != captured[1]


@pytest.mark.asyncio
async def test_origin_id_not_leaked_after_scope_exit():
    """After a chain scope exits, no origin_id remains active in the context."""
    assert get_origin_id() is None
    with origin_id_scope("temp"):
        assert get_origin_id() == "temp"
    assert get_origin_id() is None


def test_subject_has_no_origin_id_surface():
    """
    origin_id belongs to the event chain, not to the Subject: the Subject class
    must expose no origin_id constructor parameter, field, or attribute.
    """
    container = KRulesContainer()
    subject = container.subject("s")

    assert "origin_id" not in inspect.signature(Subject.__init__).parameters
    assert not hasattr(subject, "origin_id")
