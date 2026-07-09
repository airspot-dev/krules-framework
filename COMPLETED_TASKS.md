# Completed Tasks

## origin-id (cleanup phase) — remove event_info/event_data

**Date:** 2026-05-12
**Branch:** `feature/origin-id`

Removed the legacy `event_info` and `event_data` parameters from the Subject API and surrounding code. These parameters were stored on the Subject but never persisted (storage backends ignored them) and the only field ever consumed downstream was `originid`, used by CloudEvents publishers/dispatchers to preserve event-chain identity. Their persistence on the Subject was conceptually wrong: chain tracking belongs to the event context, not to subject state. A dedicated `origin_id` mechanism will be introduced in a separate task; for now publishers emit `originid` equal to each event's own id.

**What was done:**
- Removed `event_info` and `event_data` constructor parameters, `_event_info` field, and `event_info()` method from `Subject`.
- Simplified storage factory signatures (`empty_storage`, `redis_subjects_storage`, `postgres_subjects_storage`) by dropping the `**kwargs` absorption used to accept the dead parameters.
- Removed `subject.event_info()` reads from `krules_cloudevents` and `krules_cloudevents_pubsub` publishers and route dispatchers; `originid` now equals the freshly generated event id.
- Cleaned the PubSub subscriber: no longer extracts CloudEvent attributes into `event_info`, no longer passes them to the subject factory, no longer injects a `_event_info` field into the payload.
- Updated docstrings, README, API reference, container DI guide, storage backends guide, migration guide, and the cloudevents README to reflect the new state.
- Removed obsolete tests that exercised the removed parameters and the now-gone originid-preservation behaviour; simplified one test to assert the new "originid equals event id" semantics.

## Introduce origin_id for transparent event-chain tracking

**Date:** 2026-07-09
**Branch:** `feature/introduce-origin-id-for-transparent-event-chain-tracking`

Introduced a first-class `origin_id` that identifies an event chain — the whole causal sequence of events triggered by a single originating request — and propagates it transparently across the async chain and, via the `originid` CloudEvent extension, across process/transport boundaries. This is the dedicated mechanism foreshadowed by the earlier event_info/event_data cleanup: chain identity now lives in the event context, never on the Subject. Propagation is built on `contextvars` (task-local, inherited across `await`, isolated between concurrent tasks) with no external dependency.

**What was done:**
- Added `krules_core/origin.py`: a module-level `ContextVar` plus the public API `get_origin_id()` and `origin_id_scope(value=None)` (context manager, token-based reset, auto-generates a UUID root when no value is given), with `generate_origin_id()` and a lower-level `set_origin_id`/`reset_origin_id` pair.
- `EventContext` gained a typed `origin_id` field. `EventBus.emit()` opens a fresh root scope when no chain is active — so implicit events (`Subject.set()`/`delete()`) and nested `ctx.emit()` inherit the same id with no manual threading — and inherits without resetting when a chain is already active.
- CloudEvents publishers (HTTP and PubSub) now emit the chain's `origin_id` as the `originid` extension, decoupled from the per-message CloudEvent `id` (falls back to the message id only outside any active chain).
- Inbound edges re-seed the chain: the PubSub subscriber and the FastAPI CloudEvents receiver extract the incoming `originid` and open an `origin_id_scope()` per message before emitting locally.
- The Subject class keeps no origin_id surface (constructor, field, or method) — verified by test.
- Documentation: new `krules_core.origin` section and `EventContext.origin_id` attribute in the API reference; a "Chain tracking" subsection in Core Concepts.
- Tests (`tests/test_core_v2/test_origin_id.py`): concurrent-chain isolation, implicit inheritance via `ctx.emit()` and `Subject.set()`, independent roots for sequential top-level emits, no leakage after scope exit, and absence of any Subject surface. Verified end-to-end against real Google Cloud Pub/Sub, including a round-trip proving the chain `origin_id` travels as `originid` and is re-seeded on the subscriber side.

Known pre-existing limitation (out of scope): the HTTP CloudEvents dispatcher is a sync `def` that calls the async `subject.get_ext_props()` without awaiting it, so it fails before reaching the origin_id logic; making the HTTP dispatcher async is separate work.
