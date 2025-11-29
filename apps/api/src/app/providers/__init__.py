"""
Provider interfaces and implementations

Providers abstract away external/internal model services:
- EmbeddingProvider: text → vectors
- RerankProvider: query + docs → ranked list  
- LLMProvider: messages → response (already exists in adapters)

Local services (OCR, ASR, vision) are configured via settings.py,
not stored in database.
"""
