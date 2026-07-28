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

## Clarify that subject-property-changed is emitted only on actual change

**Date:** 2026-07-28
**Branch:** `feature/skill-doc-property-changed-emitted-only-on-change`

Aligned documentation and docstrings with the real emission rule of `Subject.set()`: the `subject-property-changed` event fires only when the new value differs from the current one. Several documents asserted or implied that every `.set()` emits, which is false and leads to two opposite mistakes — using `set()` as a trigger to force a handler to run, and defensively re-checking a change the framework already guarantees. No behaviour was changed; only the documentation was made truthful.

**What was done:**
- `krules_core/subject/storaged_subject.py`: docstrings for `set()` (emission conditional on `value != old_value` and `muted`, with an example of the silent re-set), `set_ext()` (never emits — metadata outside the reactive flow), and `delete()` (emits on every successful call, no comparison; added the `AttributeError` case for a missing property).
- `docs/SUBJECTS.md`: replaced the false "Every `.set()` emits ..." claim; rewrote the *Property Change Events* section with the rule, its practical consequences, Python `!=` semantics, the `old_value is None` case for a new property, and a comparison table of `set()` / `delete()` / `set_ext()`.
- `docs/CORE_CONCEPTS.md`: disambiguated the Subjects intro, the `set("temperature")` example, and the event cascade example; corrected the "state changes are events" principle.
- `docs/API_REFERENCE.md`: added **Events** notes to `set()` and `delete()`, plus **Raises** for `delete()`.
- `README.md`: aligned the Subjects paragraph (the "Events on Change Only" bullet was already correct).

Companion commit in the `airspot-skills` repository (`krules-python` skill): new *Change-Only Emission* section in `SUBJECTS.md`, antipattern §9 rewritten and inverted from "Ignoring Value Changes" to "Assuming `set()` Always Emits", rule surfaced in `SKILL.md`, and removal of the redundant `@when(old_value != new_value)` guards that had been copied into `REFERENCE.md` and `HANDLERS.md`.
