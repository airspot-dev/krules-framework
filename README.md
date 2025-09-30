# KRules Framework

KRules Framework is a comprehensive suite of tools developed by Airspot for building event-driven applications. It provides a robust foundation for managing state-driven reactive systems in distributed environments.

## Overview

KRules Framework enables:
- Persistent shared state management across multiple entities (subjects)
- Reactive service ecosystem responding to entity state changes
- Rule engine based on filter-action patterns
- Context-aware rule execution for specific entities

## Installation

Install the base package:
```bash
pip install krules-framework
```

With optional features:
```bash
# Google Cloud Pub/Sub support
pip install "krules-framework[pubsub]"

# FastAPI integration
pip install "krules-framework[fastapi]"

# Redis storage backend
pip install "krules-framework[redis]"
```

## Features

### Subject Management
- Define and manage entities (subjects) with persistent state
- Track and react to state changes
- Distributed state sharing capabilities

### Rule Engine
- Filter-Action based rule processing
- Context-aware rule execution
- Entity-specific rule application
- State change reactive patterns

### Event Processing
- Event-driven architecture support
- Cloud Events compatibility
- Google Cloud Pub/Sub integration
- FastAPI endpoints for HTTP triggers

## Requirements

- Python >=3.11
- See `pyproject.toml` for detailed dependency information

## License

Apache License 2.0

## Internal Use Notice

This package is published on PyPI for internal Airspot development convenience. While publicly available, it is primarily maintained for and used within Airspot's development ecosystem.

---

Developed and maintained by [Airspot](mailto:info@airspot.tech)