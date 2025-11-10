# Changelog

All notable changes to KRules Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
