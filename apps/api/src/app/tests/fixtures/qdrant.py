"""
Фикстуры для Qdrant интеграционных тестов.
"""
import pytest
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance


@pytest.fixture(scope="session")
def qdrant_client():
    """Предоставляет клиент Qdrant для тестов."""
    import time
    import requests
    
    # Ждем пока Qdrant будет готов
    max_retries = 30
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            # Проверяем health endpoint
            response = requests.get("http://qdrant-test:6333/health", timeout=5)
            if response.status_code == 200:
                break
        except (requests.exceptions.RequestException, requests.exceptions.Timeout):
            pass
        
        if attempt < max_retries - 1:
            time.sleep(retry_delay)
    else:
        pytest.skip("Qdrant service is not ready after maximum retries")
    
    # Создаем клиент с увеличенным таймаутом
    client = QdrantClient(
        host="qdrant-test", 
        port=6333,
        timeout=60  # Увеличиваем таймаут до 60 секунд
    )
    try:
        # Проверяем подключение
        client.get_collections()
        yield client
    except Exception as e:
        pytest.skip(f"Qdrant client creation failed: {e}")
    finally:
        try:
            client.close()
        except:
            pass


@pytest.fixture
def clean_qdrant(qdrant_client):
    """Очищает Qdrant перед каждым тестом."""
    # Получаем все коллекции
    collections = qdrant_client.get_collections()
    
    # Удаляем тестовые коллекции
    for collection in collections.collections:
        if collection.name.startswith("test_"):
            try:
                qdrant_client.delete_collection(collection.name)
            except:
                pass
    
    yield
    
    # Очистка после теста
    collections = qdrant_client.get_collections()
    for collection in collections.collections:
        if collection.name.startswith("test_"):
            try:
                qdrant_client.delete_collection(collection.name)
            except:
                pass


@pytest.fixture
def test_collection_name():
    """Генерирует уникальное имя коллекции для теста."""
    return f"test_collection_{uuid.uuid4().hex[:8]}"
