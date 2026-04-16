"""
ExtractorRegistry — extensible document extraction system.

Usage:
    from app.services.extractors import ExtractorRegistry

    result = ExtractorRegistry.extract(data, filename)
"""
from app.services.extractors.registry import ExtractorRegistry
from app.services.extractors.base import BaseExtractor, ExtractResult

__all__ = ["ExtractorRegistry", "BaseExtractor", "ExtractResult"]
