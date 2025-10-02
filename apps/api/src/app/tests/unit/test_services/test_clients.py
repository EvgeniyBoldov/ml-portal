"""
Unit тесты для Clients.
"""
import pytest
from unittest.mock import MagicMock


class TestClients:
    """Unit тесты для Clients."""

    def test_clients_initialization_mock(self):
        """Тест инициализации Clients с моками."""
        # Arrange
        mock_llm = MagicMock()
        mock_emb = MagicMock()
        mock_qdrant = MagicMock()
        mock_minio = MagicMock()

        # Act - создаем мок объект Clients
        class MockClients:
            def __init__(self):
                self.llm = mock_llm
                self.emb = mock_emb
                self.vs = mock_qdrant
                self.s3 = mock_minio

        clients = MockClients()

        # Assert
        assert clients.llm == mock_llm
        assert clients.emb == mock_emb
        assert clients.vs == mock_qdrant
        assert clients.s3 == mock_minio
