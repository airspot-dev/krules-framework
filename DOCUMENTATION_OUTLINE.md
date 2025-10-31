# KRules Framework - Documentation Outline

## Target Audience
- Internal developers (primary)
- External developers (secondary)
- AI models (Claude, etc.) for developer support

## Documentation Structure

### Root Documentation (/)

#### 1. **README.md** (Main entry point)
- What is KRules Framework
  - Async-first event-driven framework for Python
  - Reactive property store with automatic event emission
  - Decorator-based handler system
- Key features
  - Type-safe, modern Python (3.11+)
  - Container-based dependency injection
  - Pluggable storage backends
  - Production-ready (async/await, middleware, error handling)
- Quick installation
- Minimal working example (complete, runnable)
- Documentation navigation (TOC)
- License & contributing

#### 2. **QUICKSTART.md** (5-minute tutorial)
- Installation
- Container setup
- Create a subject
- Define event handlers
- Emit events
- React to property changes
- Complete runnable example
- What's next (links to deep dives)

#### 3. **CORE_CONCEPTS.md** (Architectural fundamentals)
- Framework Philosophy
  - Event-driven paradigm
  - Reactive state management
  - Separation of concerns
- The Three Core Components
  - **Subjects** - Dynamic entities with reactive state
  - **Event Bus** - Event routing and pattern matching
  - **Handlers** - Event reactions with filters
- How Components Interact
  - Event flow (text diagram)
  - Property changes trigger events
  - Event cascades
- When to Use KRules
  - Use cases (IoT, microservices, workflows, automation)
  - What KRules is NOT

#### 4. **SUBJECTS.md** (Reactive Property Store)
- What is a Subject
  - Dynamic entity with persistent state
  - Schema-less properties
  - Automatic event emission on changes
- Creating Subjects
  - via Container: `container.subject("name")`
  - Subject naming strategies
- Working with Properties
  - Setting values (simple types, nested objects)
  - Lambda values for atomic operations
  - Getting properties with defaults
  - Deleting properties
  - Checking existence
- Property Types
  - Default properties (reactive, emit events)
  - Extended properties (metadata, no events)
- Caching & Performance
  - Caching strategy explained
  - `use_cache` parameter
  - Batch operations pattern
  - When to call `.store()`
- Property Change Events
  - Automatic `subject-property-changed` emission
  - Event payload structure
  - Muted properties (no event emission)
- Advanced Operations
  - `.flush()` - delete subject entirely
  - `.dict()` - export state
  - Iteration over properties
- AwaitableResult Pattern
  - Sync vs async contexts
  - When and why to await
- Subject Lifecycle

#### 5. **EVENT_HANDLERS.md** (Declarative Event Processing)
- Handler Registration
  - `@on(*patterns)` decorator
    - Single event: `@on("user.login")`
    - Multiple events: `@on("user.created", "user.updated")`
    - Glob patterns: `@on("device.*")`
    - Wildcard: `@on("*")`
  - Getting decorators from container
- Filters (Conditional Execution)
  - `@when(*conditions)` decorator
  - Single filter
  - Multiple filters (AND logic)
  - Reusable filter functions
  - Async filters
  - Property change filters
- Decorator Stacking
  - Order doesn't matter
  - Multiple `@when` on same handler
- EventContext
  - Available attributes
    - `event_type`, `subject`, `payload`
    - `property_name`, `old_value`, `new_value` (for property events)
  - Methods
    - `ctx.emit()` - emit new events
    - `ctx.get_metadata()` / `ctx.set_metadata()`
- Handler Execution
  - Async handlers (recommended)
  - Sync handlers (supported)
  - Execution order
  - Error isolation (one handler error doesn't block others)
- Emitting Events
  - `emit()` function from container
  - Direct emission (outside handlers)
  - With extra metadata

#### 6. **MIDDLEWARE.md** (Cross-cutting Concerns)
- What is Middleware
  - Intercepts all events
  - Chain of responsibility pattern
- Defining Middleware
  - `@middleware` decorator
  - Signature: `async def mw(ctx, next)`
- Middleware Chain
  - Execution order
  - Calling `next()`
  - Short-circuiting
- Common Use Cases
  - Logging & tracing
  - Performance timing
  - Authentication/authorization
  - Error handling & recovery
  - Metrics & monitoring
- Examples
  - Timing middleware
  - Error catching middleware
  - Request context middleware

#### 7. **CONTAINER_DI.md** (Dependency Injection)
- Why Dependency Injection
  - Testability
  - Flexibility
  - Separation of concerns
- KRulesContainer Overview
  - Declarative container pattern
  - Provider types (Singleton, Factory, Callable)
- Container Providers
  - `event_bus` - Singleton EventBus
  - `subject_storage` - Storage factory (callable)
  - `subject` - Subject factory
  - `handlers` - Returns (on, when, middleware, emit)
- Using the Container
  - Basic usage
  - Getting handlers
  - Creating subjects
- Overriding Providers
  - Storage backend override
  - Custom event bus
  - Override examples (Redis, custom storage)
- Advanced Patterns
  - Multiple containers
  - Container composition
  - Testing with containers

#### 8. **STORAGE_BACKENDS.md** (Persistence Layer)
- Storage Interface
  - Required methods
    - `load()` - retrieve subject state
    - `store(inserts, updates, deletes)` - batch persist
    - `set()` - atomic property set
    - `get()` - retrieve property
    - `delete()` - delete property
    - `flush()` - delete entire subject
    - `get_ext_props()` - get extended properties
  - Optional metadata
    - `is_concurrency_safe()`
    - `is_persistent()`
- Built-in Storage: EmptySubjectStorage
  - In-memory, non-persistent
  - Use case: development, testing
- Redis Storage: SubjectsRedisStorage
  - Configuration (URL, key prefix)
  - Key structure in Redis
  - Atomic operations (WATCH/MULTI)
  - Connection management
  - Performance characteristics
- Implementing Custom Storage
  - Interface implementation guide
  - Example skeleton (SQLite-based)
  - Best practices
    - Concurrency handling
    - Error handling
    - Performance optimization
- Configuring Storage in Container
  - Storage factory pattern
  - Override examples

#### 9. **INTEGRATIONS.md** (Framework Extensions)
- FastAPI Integration (`krules_fastapi_env`)
  - Setup & initialization
  - Request-scoped containers
  - Endpoint patterns
  - Dependency injection in routes
  - Example application
- Google Cloud Pub/Sub (`krules_pubsub`)
  - Publisher configuration
  - Subscriber configuration
  - Topic management
  - Error handling & retries
- CloudEvents (`krules_cloudevents`)
  - CloudEvents specification support
  - Creating CloudEvents
  - Parsing CloudEvents
  - Attribute mapping
- Pub/Sub + CloudEvents (`krules_cloudevents_pubsub`)
  - Combined integration
  - Publishing events as CloudEvents
  - Subscribing to CloudEvents
  - Serialization/deserialization
- Building Custom Integrations
  - Event source integration pattern
  - Event sink integration pattern

#### 10. **TESTING.md** (Testing Strategies)
- Testing Philosophy
  - Unit test handlers in isolation
  - Integration test event flows
  - Mock storage for speed
- Handler Testing
  - `reset_event_bus()` utility
  - Isolated handler registration
  - Pytest fixtures
  - Async test setup (`pytest.mark.asyncio`)
- Subject Testing
  - Using EmptySubjectStorage
  - Property assertion patterns
  - Event emission verification
- Event Flow Testing
  - Multi-handler scenarios
  - Event cascade testing
  - Middleware testing
- Storage Backend Testing
  - Testing custom storage implementations
  - Redis testing with testcontainers
- Complete Examples
  - Handler test
  - Event flow test
  - Middleware test

#### 11. **ADVANCED_PATTERNS.md** (Production Best Practices)
- Event Cascade Design
  - Planning event flows
  - Avoiding infinite loops
  - Circuit breaker patterns
  - Event naming conventions
- Error Handling
  - Per-handler error isolation
  - Global error middleware
  - Dead letter queue patterns
  - Retry strategies
- Performance Optimization
  - Batch property updates
  - Cache usage strategies
  - Handler concurrency
  - Storage backend tuning
- Monitoring & Observability
  - Logging middleware
  - Metrics collection
  - Distributed tracing
  - Event debugging
- Scalability
  - Horizontal scaling patterns
  - Event partitioning
  - Storage sharding
  - Load balancing

#### 12. **SHELL_MODE.md** (Interactive/REPL Usage)
- Overview
  - Convenience syntax for interactive use
  - NOT for production code
- Attribute Access Syntax
  - `subject.property` (get)
  - `subject.property = value` (set)
  - `del subject.property` (delete)
- Special Prefixes
  - `subject.m_property` - muted (no event emission)
  - `subject.ext_property` - extended property
- SubjectPropertyProxy
  - Auto-wrapping of property values
  - `.incr(amount=1)` for counters
  - `.decr(amount=1)` for counters
- Limitations
  - Property names with special characters
  - Python keywords
  - Dynamic property names
  - Type checking limitations
- Use Cases
  - Interactive debugging
  - REPL exploration
  - Quick prototyping
  - Shell scripts (with caution)
- Examples

#### 13. **API_REFERENCE.md** (Complete API Documentation)
- Organized by module
- Type signatures for all public APIs
- Brief descriptions
- Links to detailed docs

**Sections:**
- `krules_core.container.KRulesContainer`
- `krules_core.event_bus.EventBus`
- `krules_core.event_bus.EventContext`
- `krules_core.subject.storaged_subject.Subject`
- `krules_core.handlers` (on, when, middleware, emit)
- Storage interface
- Utility functions

Each entry includes:
- Signature with types
- Parameters
- Return type
- Brief description
- Link to detailed documentation

---

### Module-Specific READMEs

#### krules_cloudevents/README.md
- CloudEvents support for KRules
- Installation
- Usage examples
- CloudEvent structure
- API reference

#### krules_pubsub/README.md
- Google Pub/Sub integration
- Installation & setup
- Publisher configuration
- Subscriber configuration
- Examples

#### krules_cloudevents_pubsub/README.md
- Combined Pub/Sub + CloudEvents
- Installation
- Publishing CloudEvents
- Subscribing to CloudEvents
- Complete example

#### krules_fastapi_env/README.md
- FastAPI integration
- Installation
- Setup & configuration
- Request lifecycle
- Examples

#### redis_subjects_storage/README.md
- Redis storage backend
- Installation
- Configuration
- Key structure
- Performance tuning
- Connection pooling

---

## Documentation Principles

1. **Present, Not Past**
   - Document the framework as it is now
   - No comparisons with previous versions (except MIGRATION.md)
   - Focus on current capabilities

2. **AI-Friendly**
   - Complete type signatures
   - Self-contained examples
   - Explicit patterns & anti-patterns
   - Structured reference

3. **Developer-Focused**
   - Examples-driven
   - Real-world patterns
   - Edge cases documented
   - Pragmatic, not academic

4. **Concise & Technical**
   - Assume experienced Python developers
   - No hand-holding on Python basics
   - Direct, clear language
   - Focus on KRules-specific concepts

---

## Separate: MIGRATION.md

- Keep existing MIGRATION.md for users upgrading from 1.x
- NOT linked prominently in main docs
- Available for those who need it
- Not part of main documentation narrative

---

## Next Steps

1. Review & approve this revised outline
2. Answer open questions (examples domain, diagram style, etc.)
3. Choose approach (pilot doc vs sequential vs parallel)
4. Start writing
