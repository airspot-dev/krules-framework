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
Transparent origin_id propagation for event chains.

An ``origin_id`` identifies an *event chain*: the whole causal sequence of
events triggered, directly or indirectly, by a single originating request.
It propagates implicitly across the async chain within a process, and is
mapped onto the ``originid`` CloudEvent extension attribute when a chain
crosses a process/transport boundary.

The mechanism is built on the standard library ``contextvars.ContextVar``,
which provides task-local storage automatically inherited across ``await``
boundaries within the same asyncio task and isolated between concurrent
tasks. No external dependency is required.

Two public primitives:

- :func:`get_origin_id` — read the current chain's origin_id (or ``None``).
  Use it to *serialize* the id when a chain must cross a boundary the
  ContextVar cannot traverse (a message broker, a scheduler, a datastore).
- :func:`origin_id_scope` — establish (or resume) a chain scope. Use it at
  *entry points* to seed the id from an incoming ``originid`` (or auto-generate
  a new root), and to *re-seed* a chain on the receiving side of a boundary.

``EventBus.emit()`` reads the ContextVar and, when no chain is active, opens a
fresh scope for the duration of the emit so that implicit events (property
changes, deletions) and nested emits inherit the same id with no manual
threading. The Subject class deliberately has no origin_id surface: the id
belongs to the chain, not to any Subject.
"""

import contextlib
import uuid
from contextvars import ContextVar, Token
from typing import Iterator, Optional

# Task-local storage for the current chain's origin_id.
# default=None means "no chain active in this context".
_origin_id_var: ContextVar[Optional[str]] = ContextVar(
    "krules_origin_id", default=None
)


def generate_origin_id() -> str:
    """Mint a new origin_id for a brand-new chain root."""
    return str(uuid.uuid4())


def get_origin_id() -> Optional[str]:
    """
    Return the origin_id of the chain active in the current context,
    or ``None`` if no chain is active.

    Read this to surface the id to user code, or to serialize it when a chain
    must cross a boundary the ContextVar cannot traverse (message broker,
    scheduler, datastore) — the receiving side re-seeds it via
    :func:`origin_id_scope`.
    """
    return _origin_id_var.get()


def set_origin_id(value: str) -> Token:
    """
    Set the current chain's origin_id, returning a token for :func:`reset_origin_id`.

    Prefer :func:`origin_id_scope` where a ``with`` block fits; use this
    lower-level pair only when the set/reset cannot be lexically scoped.
    """
    return _origin_id_var.set(value)


def reset_origin_id(token: Token) -> None:
    """Restore the origin_id to the value held before the matching :func:`set_origin_id`."""
    _origin_id_var.reset(token)


@contextlib.contextmanager
def origin_id_scope(value: Optional[str] = None) -> Iterator[str]:
    """
    Establish an origin_id chain scope for the duration of the ``with`` block.

    Args:
        value: The origin_id to seed. If ``None``, a new one is generated
            (a new chain root). Pass an incoming ``originid`` here to continue
            a remote chain on the receiving side of a boundary.

    Yields:
        The active origin_id (the passed value, or the freshly generated one).

    The previous value is restored on exit (token reset), so nested scopes,
    sequential scopes in the same task, and concurrent tasks all stay isolated.

    Example (entry point — seed from an incoming CloudEvent, or auto-generate)::

        with origin_id_scope(incoming_originid):   # None -> new root
            await event_bus.emit(event_type, subject, payload)

    Example (re-seed on the far side of a broker/scheduler boundary)::

        with origin_id_scope(serialized_root):
            await dispatch(...)
    """
    if value is None:
        value = generate_origin_id()
    token = _origin_id_var.set(value)
    try:
        yield value
    finally:
        _origin_id_var.reset(token)
