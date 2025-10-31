"""
KRules FastAPI Integration

Provides FastAPI integration for KRules framework with container-first pattern.

Main exports:
- KrulesApp: FastAPI application with KRules integration
"""

from .app import KrulesApp

__all__ = ['KrulesApp']
