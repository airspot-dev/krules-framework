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
