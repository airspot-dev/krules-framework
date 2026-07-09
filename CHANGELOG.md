# Changelog

All notable changes to KRules Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.2.0] - 2026-07-09

### ✨ Added

- **`origin_id` — transparent event-chain tracking**
  - Introduced a first-class `origin_id` that identifies an entire event chain (the causal sequence of events triggered by a single originating request) and propagates it transparently across the async chain and, via the `originid` CloudEvent extension, across process/transport boundaries.
  - New module `krules_core/origin.py` with a module-level `ContextVar` and public API:
    - `get_origin_id()` — read the current chain id
    - `origin_id_scope(value=None)` — context manager (token-based reset) that seeds an explicit id or auto-generates a UUID root when none is given
    - lower-level `generate_origin_id()`, `set_origin_id`/`reset_origin_id`
  - `EventContext` gained a typed `origin_id` field. `EventBus.emit()` opens a fresh root scope when no chain is active — so implicit events (`Subject.set()`/`delete()`) and nested `ctx.emit()` inherit the same id with no manual threading — and inherits without resetting when a chain is already active.
  - CloudEvents publishers (HTTP and PubSub) emit the chain's `origin_id` as the `originid` extension, decoupled from the per-message CloudEvent `id` (falls back to the message id only outside any active chain).
  - Inbound edges re-seed the chain: the PubSub subscriber and the FastAPI CloudEvents receiver extract the incoming `originid` and open an `origin_id_scope()` per message before emitting locally.
  - Propagation is built on `contextvars` (task-local, inherited across `await`, isolated between concurrent tasks) with no external dependency. Chain identity lives in the event context, never on the Subject.

### ♻️ Changed

- Removed the legacy `event_info` and `event_data` parameters from the `Subject` API and surrounding code (constructor params, `_event_info` field, `event_info()` method). These were stored on the Subject but never persisted, and chain tracking now belongs to the event context. Storage factory signatures (`empty_storage`, `redis_subjects_storage`, `postgres_subjects_storage`) were simplified accordingly.

### 📝 Documentation

- Added `krules_core.origin` API section and `EventContext.origin_id` attribute to the API reference; added a "Chain tracking" subsection to Core Concepts.
- Fixed the Celery integration docs with a production-proven pattern.

### 🧪 Testing

- Added `tests/test_core_v2/test_origin_id.py`: concurrent-chain isolation, implicit inheritance via `ctx.emit()` and `Subject.set()`, independent roots for sequential top-level emits, no leakage after scope exit, and absence of any Subject surface. Verified end-to-end against real Google Cloud Pub/Sub.

### ⚠️ Known Limitations

- The HTTP CloudEvents dispatcher is a sync `def` that calls the async `subject.get_ext_props()` without awaiting it; making it async is separate work.

## [3.1.1] - 2025-11-10

### 🐛 Bug Fixes

- **Fixed `default=None` handling in `get()` and `get_ext()`**
  - Bug: Passing `default=None` explicitly raised `AttributeError` instead of returning `None`
  - Root cause: Code could not distinguish "default not provided" from "default=None"
  - Solution: Use sentinel value (`_NOT_PROVIDED`) to distinguish the two cases
  - Now works correctly:
    - `await subject.get("missing")` → raises `AttributeError` ✓
    - `await subject.get("missing", default=None)` → returns `None` ✓ (FIXED)
    - `await subject.get("missing", default=1)` → returns `1` ✓
  - Same fix applied to `get_ext()`

### 🧪 Testing

- Added test cases for `default=None` behavior in both `get()` and `get_ext()`
- All 81 tests passing

## [3.1.0] - 2025-11-10

### ✨ Added

- **`use_cache` Parameter Restored** - Fine-grained cache control for all Subject operations
  - Added `use_cache` parameter to `get()`, `set()`, `delete()` and their `_ext` variants
  - Added `use_cache_default` parameter to `Subject.__init__()` for Subject-level defaults
  - `use_cache=False` bypasses cache and operates directly on storage
  - `use_cache=True` uses cache (requires `await subject.store()` to persist)
  - `use_cache=None` (default) uses the Subject's `use_cache_default` setting

- **Direct Storage Operations** - When `use_cache=False`:
  - Writes immediately persist to storage (Redis, PostgreSQL)
  - Reads fetch fresh data from storage, bypassing any cached values
  - Deletes immediately remove from storage
  - Atomic operations with callables use storage-level transactions (Redis WATCH/MULTI/EXEC, PostgreSQL SELECT FOR UPDATE)
  - Cache automatically synchronized when present

- **Cross-Process Coordination** - `use_cache=False` enables:
  - Distributed counters with atomic increments
  - Fresh data reads across multiple processes/containers
  - Immediate visibility of changes to other processes
  - Lock-like patterns with immediate storage writes

### 📚 Documentation

- Expanded `docs/SUBJECTS.md` with comprehensive caching documentation
  - Per-operation cache control examples
  - Subject-level cache control patterns
  - Cache synchronization behavior
  - Distributed systems use cases
- Updated `docs/API_REFERENCE.md` with complete method signatures
- Updated krules-claude-skill with `use_cache` examples

### 🧪 Testing

- Added 9 comprehensive tests for `use_cache` functionality
- Created `InMemoryTestStorage` helper for persistent test storage
- All 27 Subject tests passing, 81 total tests passing

### 🔧 Technical Details

This release restores the `use_cache` functionality that existed in v2.x but was inadvertently lost during the v3.0 async migration. All changes are **fully backward compatible** - existing code continues to work unchanged as the default behavior remains `use_cache=True` (cache-first).

**Use Cases:**
```python
# Immediate persistence (critical data)
await subject.set("signal", "BUY", use_cache=False)

# Fresh data from storage (multi-process)
price = await subject.get("price", use_cache=False)

# Atomic distributed counter
await counter.set("count", lambda c: (c or 0) + 1, use_cache=False)

# Subject-level control
subject = Subject(..., use_cache_default=False)  # All ops bypass cache by default
```

## [3.0.0] - 2025-11-10

### 🚀 Major Changes - Async-Only API

KRules v3.0.0 is a **major breaking release** that makes the framework fully async. All Subject operations now require `await`.

### ✨ Added

- **PostgreSQL Storage Backend** - New storage backend with JSONB support for flexible property storage
  - Atomic operations with SELECT FOR UPDATE
  - Automatic schema creation on first use
  - Full JSONB indexing with GIN indexes
  - Connection pooling with asyncpg
  - See `postgres_subjects_storage/` package

- **Extra Context Parameter** - Pass additional context to event handlers
  - New `extra` parameter on `Subject.set()` and `Subject.delete()`
  - Accessible via `ctx.extra` in handlers
  - Use cases: audit trails, business context, debugging metadata
  - Example: `await subject.set("status", "suspended", extra={"reason": "policy", "admin_id": "123"})`

- **Comprehensive Jupyter Notebook** - Interactive showcase of all framework features
  - Located at `examples/krules_showcase.ipynb`
  - Demonstrates subjects, handlers, storage backends
  - Complete order processing workflow example

- **Migration Guide** - Complete v2 to v3 migration documentation
  - Step-by-step upgrade process
  - Breaking changes documented
  - Automated migration scripts
  - Rollback plan included
  - See `docs/MIGRATION_V3.md`

### ⚠️ Breaking Changes

#### 1. All Subject Methods Are Now Async

**Before (v2.x):**
```python
subject.set("name", "John")
subject.get("name")
subject.store()
```

**After (v3.0):**
```python
await subject.set("name", "John")
await subject.get("name")
await subject.store()
```

**Impact:** All code using Subject operations must be updated to use `await`.

#### 2. Redis Storage API Changed

**Before (v2.x):**
```python
create_redis_storage(
    redis_url="redis://localhost:6379",
    redis_prefix="myapp:"
)
```

**After (v3.0):**
```python
redis_client = Redis.from_url("redis://localhost:6379")
create_redis_storage(
    redis_client=redis_client,
    redis_prefix="myapp:"
)
```

**Impact:** Container configuration needs to be updated to create Redis client first.

### 📝 Changed

- **Documentation Reorganized** - All docs moved to `docs/` directory
  - Improved structure and navigation
  - Added Quick Start, Core Concepts, Migration guides
  - Removed obsolete Shell Mode documentation
  - Updated all examples to async API

- **Storage Interface Updated** - All storage methods are now async
  - `async def load()`, `async def store()`, `async def set()`, etc.
  - Both Redis and PostgreSQL implementations fully async
  - Better concurrency support

- **Event Handlers** - All handlers should be async functions
  - Use `async def handler(ctx): ...`
  - Handlers can now properly await async operations
  - Better error handling in async context

### 🔧 Fixed

- **Subject Property Events** - Events now only fire when values actually change
- **EventContext** - Fixed `ctx.emit()` parameter order in documentation examples
- **Redis Storage** - Removed incorrect `decode_responses=True` from examples
- **PostgreSQL Examples** - Fixed atomic operation examples in notebook

### 📚 Documentation

- Complete async API reference
- PostgreSQL storage setup guide
- Redis storage updated for v3.0 API
- Extra context usage examples
- Migration checklist and tools
- Comprehensive CHANGELOG (this file)

### 🧪 Testing

- All 132 core tests passing
- Added tests for extra context parameter
- PostgreSQL storage comprehensive test coverage
- Concurrent operations verified (50+ concurrent increments)
- Zero lost updates in atomicity tests

### 📦 Dependencies

- Added `asyncpg>=0.30.0` for PostgreSQL support (optional extra)
- Updated `redis` to use `redis.asyncio` for async client
- Added `jupyter` and `notebook` to dev dependencies

### 🔗 Migration

See [MIGRATION_V3.md](docs/MIGRATION_V3.md) for complete upgrade guide.

**Quick migration checklist:**
- [ ] Add `await` to all Subject operations
- [ ] Update Redis storage API in container
- [ ] Make all handlers `async def`
- [ ] Run tests to verify async usage
- [ ] Review breaking changes documentation

---

## [2.0.0] - 2024-11-05

### 🚀 Major Changes - Container-First Architecture

KRules v2.0.0 introduced a **container-first dependency injection** pattern using `dependency-injector`.

### ✨ Added

- **Container-First DI Pattern** - Embed KRulesContainer inside main application container
  - Use `providers.Container(KRulesContainer)` pattern
  - Access both KRules and app services from handlers
  - Better testability and maintainability

- **Improved Storage Architecture** - Cleaner storage backend interface
  - Standardized storage methods
  - Better concurrency support
  - Redis storage with optimistic locking

- **Async/Await Support** - Initial async support for handlers
  - Handlers can be async functions
  - Middleware supports async
  - Event emission supports async

- **Comprehensive Documentation** - Complete documentation overhaul
  - Architecture patterns
  - Configuration with pydantic-settings
  - Integration examples (Celery, FastAPI, Pub/Sub)
  - Anti-patterns and troubleshooting

### ⚠️ Breaking Changes

- **Container Pattern Required** - Direct KRulesContainer instantiation discouraged
- **Import Changes** - Some imports reorganized
- **Configuration** - Moved to pydantic-settings pattern
- **Storage Interface** - Custom storage backends need updates

### 🔧 Changed

- **Event Bus** - Improved event routing and handler management
- **Middleware** - Cleaner middleware API
- **Testing** - Better test utilities and fixtures

### 🗑️ Removed

- **krules_env** - Legacy initialization layer removed
- **Legacy patterns** - Old global container patterns deprecated

### 📚 Documentation

- Full architecture documentation
- Container-in-Container pattern guide
- Configuration with pydantic-settings
- Handler patterns and examples
- Storage backend development guide

---

## [1.1.0] - 2024-XX-XX

### ✨ Added

- Redis/Valkey as default subjects storage layer
- Event bus pub/sub middleware
- Dependency injection improvements
- Python 3.13 support

### 🔧 Changed

- Upgraded dependency-injector for Python 3.13
- General dependencies upgrade
- Subject methods improvements

---

## [1.0.4] - 2024-XX-XX

### 🔧 Bug Fixes

- Various stability improvements
- Documentation updates

---

## [1.0.3] - 2024-XX-XX

### 🔧 Bug Fixes

- Minor fixes and improvements

---

## [1.0.2] - 2024-XX-XX

### 🔧 Bug Fixes

- Bug fixes and stability improvements

---

## [1.0.1] - 2024-XX-XX

### ✨ Initial Release

- Initial stable release of KRules Framework
- Core event-driven architecture
- Subject property management
- Event handlers and filters
- Middleware support
- Redis storage backend

---

## Version Links

- [3.0.0]: Latest - Async-only API with PostgreSQL support
- [2.0.0]: Container-first architecture
- [1.1.0]: Redis/Valkey storage improvements
- [1.0.x]: Initial stable releases

## Getting Help

- **Documentation**: [docs/](docs/)
- **Migration Guides**: [docs/MIGRATION_V3.md](docs/MIGRATION_V3.md)
- **GitHub Issues**: Report bugs and request features
- **Support**: info@airspot.tech
