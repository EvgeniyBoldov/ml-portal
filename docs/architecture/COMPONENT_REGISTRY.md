# Реестр компонентов ML Portal

## Обзор
Этот документ содержит реестр всех компонентов системы с их интерфейсами, зависимостями и контрактами.

## Легенда
- ✅ **Готово** - компонент реализован и протестирован
- 🚧 **В работе** - компонент в процессе разработки
- ⏳ **Планируется** - компонент запланирован к реализации
- ❌ **Проблемы** - компонент имеет критические проблемы

---

## Этап 1: Базовые коннекторы и утилиты

### 1.1 Конфигурация и настройки

#### `apps/api/src/app/core/config.py`
- **Статус**: ⏳ Планируется
- **Описание**: Центральная конфигурация приложения
- **Зависимости**: Нет
- **Интерфейс**:
  ```python
  class Config:
      # Database
      database_url: str
      database_pool_size: int = 10
      
      # Redis
      redis_url: str
      redis_db: int = 0
      
      # S3
      s3_endpoint: str
      s3_access_key: str
      s3_secret_key: str
      s3_bucket: str
      
      # Security
      secret_key: str
      access_token_expire_minutes: int = 30
      
      # External services
      qdrant_url: str
      llm_service_url: str
      emb_service_url: str
  ```

#### `apps/api/src/app/core/env.py`
- **Статус**: ⏳ Планируется
- **Описание**: Загрузка переменных окружения
- **Зависимости**: Нет
- **Интерфейс**:
  ```python
  def load_env() -> dict[str, Any]
  def get_env_var(key: str, default: Any = None) -> Any
  def validate_required_env_vars(required: list[str]) -> None
  ```

#### `apps/api/src/app/core/settings.py`
- **Статус**: ⏳ Планируется
- **Описание**: Настройки сервисов
- **Зависимости**: `config.py`, `env.py`
- **Интерфейс**:
  ```python
  class Settings:
      database: DatabaseSettings
      redis: RedisSettings
      s3: S3Settings
      security: SecuritySettings
      services: ServicesSettings
  ```

### 1.2 База данных

#### `apps/api/src/app/core/db.py`
- **Статус**: ✅ Готово
- **Описание**: Подключение к базе данных с поддержкой sync/async
- **Зависимости**: `config.py`, `logging.py`
- **Интерфейс**:
  ```python
  class DatabaseManager:
      def get_session() -> Generator[Session, None, None]
      def get_async_session() -> AsyncGenerator[AsyncSession, None]
      def session_scope() -> Generator[Session, None, None]
      def async_session_scope() -> AsyncGenerator[AsyncSession, None]
      def close_all() -> None
      def close_async_all() -> None
      def health_check() -> bool
      def async_health_check() -> bool
  ```

#### `apps/api/src/app/migrations/`
- **Статус**: ⏳ Планируется
- **Описание**: Alembic миграции
- **Зависимости**: `models/`
- **Интерфейс**:
  ```bash
  alembic upgrade head
  alembic downgrade -1
  alembic revision --autogenerate -m "description"
  ```

### 1.3 Кэш и Redis

#### `apps/api/src/app/core/cache.py`
- **Статус**: ✅ Готово
- **Описание**: Система кэширования с поддержкой sync/async
- **Зависимости**: `redis.py`, `logging.py`
- **Интерфейс**:
  ```python
  class CacheManager:
      # Sync methods
      def get(key: str) -> Optional[Any]
      def set(key: str, value: Any, ttl: Optional[int] = None) -> bool
      def delete(key: str) -> bool
      def exists(key: str) -> bool
      def get_or_set(key: str, factory_func: Callable, ttl: Optional[int] = None, *args, **kwargs) -> Any
      def invalidate_pattern(pattern: str) -> int
      
      # Async methods
      async def get_async(key: str) -> Optional[Any]
      async def set_async(key: str, value: Any, ttl: Optional[int] = None) -> bool
      async def delete_async(key: str) -> bool
      async def exists_async(key: str) -> bool
      async def get_or_set_async(key: str, factory_func: Callable, ttl: Optional[int] = None, *args, **kwargs) -> Any
      async def invalidate_pattern_async(pattern: str) -> int
  ```

#### `apps/api/src/app/core/redis.py`
- **Статус**: ✅ Готово
- **Описание**: Redis подключение с поддержкой sync/async
- **Зависимости**: `config.py`, `logging.py`
- **Интерфейс**:
  ```python
  class RedisManager:
      def get_async_redis() -> Redis
      def get_sync_redis() -> SyncRedis
      async def ping_async() -> bool
      def ping_sync() -> bool
      async def close_async() -> None
      def close_sync() -> None
      async def health_check_async() -> bool
      def health_check_sync() -> bool
  ```

### 1.4 S3 и файловое хранилище

#### `apps/api/src/app/core/s3.py`
- **Статус**: ✅ Готово
- **Описание**: S3/MinIO клиент с расширенной функциональностью
- **Зависимости**: `config.py`, `logging.py`
- **Интерфейс**:
  ```python
  class S3Manager:
      def health_check() -> bool
      def ensure_bucket(bucket: str) -> bool
      def list_buckets() -> List[Dict[str, Any]]
      def put_object(bucket: str, key: str, data: Union[bytes, BinaryIO], length: Optional[int] = None, content_type: Optional[str] = None) -> bool
      def get_object(bucket: str, key: str) -> Optional[BinaryIO]
      def delete_object(bucket: str, key: str) -> bool
      def stat_object(bucket: str, key: str) -> Optional[Dict[str, Any]]
      def presign_put(bucket: str, key: str, expiry_seconds: int = 3600) -> Optional[str]
      def presign_get(bucket: str, key: str, expiry_seconds: int = 3600) -> Optional[str]
      def list_objects(bucket: str, prefix: str = "", recursive: bool = True) -> List[Dict[str, Any]]
  ```

#### `apps/api/src/app/storage/`
- **Статус**: ⏳ Планируется
- **Описание**: Файловые операции
- **Зависимости**: `s3.py`
- **Интерфейс**:
  ```python
  class FileStorage:
      async def save_file(file: UploadFile, user_id: str) -> str
      async def get_file(file_id: str) -> bytes
      async def delete_file(file_id: str)
  ```

### 1.5 Логирование и мониторинг

#### `apps/api/src/app/core/logging.py`
- **Статус**: ⏳ Планируется
- **Описание**: Система логирования
- **Зависимости**: Нет
- **Интерфейс**:
  ```python
  def get_logger(name: str) -> Logger
  def setup_logging(level: str = "INFO")
  ```

#### `apps/api/src/app/core/metrics.py`
- **Статус**: ⏳ Планируется
- **Описание**: Метрики и мониторинг
- **Зависимости**: Нет
- **Интерфейс**:
  ```python
  class MetricsCollector:
      def increment_counter(name: str, tags: dict = None)
      def record_timing(name: str, duration: float, tags: dict = None)
      def set_gauge(name: str, value: float, tags: dict = None)
  ```

---

## Этап 2: Модели данных

### 2.1 Базовые модели

#### `apps/api/src/app/models/base.py`
- **Статус**: ✅ Готово
- **Описание**: Базовая модель SQLAlchemy
- **Зависимости**: Нет
- **Интерфейс**:
  ```python
  class Base(DeclarativeBase):
      metadata = metadata
      
      @declared_attr.directive
      def __tablename__(cls) -> str
  ```

#### `apps/api/src/app/models/__init__.py`
- **Статус**: ✅ Готово
- **Описание**: Экспорты моделей
- **Зависимости**: Все модели
- **Интерфейс**:
  ```python
  from .base import Base
  from .user import Users, UserTokens, UserRefreshTokens
  from .chat import Chats, ChatMessages
  from .rag import RAGDocument, RAGChunk
  from .analyze import AnalysisDocuments, AnalysisChunks
  ```

### 2.2 Модели пользователей

#### `apps/api/src/app/models/user.py`
- **Статус**: ✅ Готово
- **Описание**: Модели пользователей и аутентификации
- **Зависимости**: `base.py`
- **Интерфейс**:
  ```python
  class Users(Base):
      id: UUID
      login: str
      password_hash: str
      role: str
      is_active: bool
      email: Optional[str]
      # ... relationships
      
  class UserTokens(Base):
      id: UUID
      user_id: UUID
      token_hash: str
      # ... other fields
      
  class UserRefreshTokens(Base):
      id: UUID
      user_id: UUID
      refresh_hash: str
      # ... other fields
  ```

### 2.3 Модели чатов

#### `apps/api/src/app/models/chat.py`
- **Статус**: ✅ Готово
- **Описание**: Модели чатов и сообщений
- **Зависимости**: `base.py`, `user.py`
- **Интерфейс**:
  ```python
  class Chats(Base):
      id: UUID
      name: Optional[str]
      owner_id: UUID
      tags: Optional[List[str]]
      # ... timestamps
      
  class ChatMessages(Base):
      id: UUID
      chat_id: UUID
      role: str
      content: dict
      # ... other fields
  ```

### 2.4 RAG модели

#### `apps/api/src/app/models/rag.py`
- **Статус**: ✅ Готово
- **Описание**: Модели RAG документов
- **Зависимости**: `base.py`
- **Интерфейс**:
  ```python
  class RAGDocument(Base):
      id: str
      filename: str
      title: str
      status: str
      user_id: str
      # ... other fields
      
  class RAGChunk(Base):
      id: str
      document_id: str
      content: str
      chunk_index: int
      # ... other fields
  ```

### 2.5 Модели анализа

#### `apps/api/src/app/models/analyze.py`
- **Статус**: ✅ Готово
- **Описание**: Модели анализа документов
- **Зависимости**: `base.py`, `user.py`
- **Интерфейс**:
  ```python
  class AnalysisDocuments(Base):
      id: UUID
      status: str
      uploaded_by: Optional[UUID]
      # ... other fields
      
  class AnalysisChunks(Base):
      id: UUID
      document_id: UUID
      text: str
      chunk_idx: int
      # ... other fields
  ```

---

## Этап 3: Репозитории (Data Access Layer)

### 3.1 Базовый репозиторий

#### `apps/api/src/app/repositories/_base.py`
- **Статус**: ✅ Готово
- **Описание**: Базовый CRUD репозиторий с поддержкой sync/async
- **Зависимости**: `models/`, `db.py`, `logging.py`
- **Интерфейс**:
  ```python
  class BaseRepository[T]:
      def create(**kwargs) -> T
      def get_by_id(id: Any) -> Optional[T]
      def get_by_field(field_name: str, value: Any) -> Optional[T]
      def update(id: Any, **kwargs) -> Optional[T]
      def delete(id: Any) -> bool
      def list(filters: Optional[Dict[str, Any]] = None, order_by: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[T]
      def count(filters: Optional[Dict[str, Any]] = None) -> int
      def exists(id: Any) -> bool
      def search(query: str, search_fields: List[str], limit: int = 100, offset: int = 0) -> List[T]
  ```

### 3.2 Репозитории пользователей

#### `apps/api/src/app/repositories/users_repo_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Расширенный репозиторий пользователей с полным функционалом
- **Зависимости**: `_base.py`, `models/user.py`, `logging.py`
- **Интерфейс**:
  ```python
  class UsersRepository(BaseRepository[Users]):
      def get_by_login(login: str) -> Optional[Users]
      def get_by_email(email: str) -> Optional[Users]
      def get_active_users() -> List[Users]
      def get_users_by_role(role: str) -> List[Users]
      def search_users(query: str, limit: int = 50) -> List[Users]
      def create_user(login: str, password_hash: str, role: str = "reader", email: Optional[str] = None, is_active: bool = True) -> Users
      def update_user_role(user_id: str, role: str) -> Optional[Users]
      def deactivate_user(user_id: str) -> Optional[Users]
      def activate_user(user_id: str) -> Optional[Users]
      def change_password(user_id: str, new_password_hash: str) -> Optional[Users]
  ```

#### `apps/api/src/app/repositories/users_repo.py`
- **Статус**: ✅ Существует (legacy)
- **Описание**: Существующий репозиторий пользователей
- **Зависимости**: `models/user.py`

### 3.3 Репозитории чатов

#### `apps/api/src/app/repositories/chats_repo_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Расширенный репозиторий чатов с полным функционалом
- **Зависимости**: `_base.py`, `models/chat.py`, `logging.py`
- **Интерфейс**:
  ```python
  class ChatsRepository(BaseRepository[Chats]):
      def create_chat(owner_id: str, name: Optional[str] = None, tags: Optional[List[str]] = None) -> Chats
      def get_user_chats(user_id: str, query: Optional[str] = None, limit: int = 100) -> List[Chats]
      def get_chat_with_messages(chat_id: str) -> Optional[Chats]
      def update_chat_name(chat_id: str, name: str) -> Optional[Chats]
      def update_chat_tags(chat_id: str, tags: List[str]) -> Optional[Chats]
      def update_last_message_at(chat_id: str) -> Optional[Chats]
      def get_chats_by_tag(user_id: str, tag: str) -> List[Chats]
      def search_chats(user_id: str, query: str, limit: int = 50) -> List[Chats]
  ```

#### `apps/api/src/app/repositories/chats_repo.py`
- **Статус**: ✅ Существует (legacy)
- **Описание**: Существующий репозиторий чатов
- **Зависимости**: `models/chat.py`

### 3.4 RAG репозитории

#### `apps/api/src/app/repositories/rag_repo_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Расширенный репозиторий RAG документов с полным функционалом
- **Зависимости**: `_base.py`, `models/rag.py`, `logging.py`
- **Интерфейс**:
  ```python
  class RAGDocumentsRepository(BaseRepository[RAGDocument]):
      def create_document(filename: str, title: str, user_id: str, content_type: Optional[str] = None, size: Optional[int] = None, tags: Optional[List[str]] = None) -> RAGDocument
      def get_user_documents(user_id: str, status: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[RAGDocument]
      def get_document_by_s3_key(s3_key: str) -> Optional[RAGDocument]
      def update_document_status(document_id: str, status: str, error_message: Optional[str] = None) -> Optional[RAGDocument]
      def search_documents(user_id: str, query: str, status: Optional[str] = None, limit: int = 50) -> List[RAGDocument]
      def get_document_stats(user_id: str) -> Dict[str, int]
  ```

#### `apps/api/src/app/repositories/rag_repo.py`
- **Статус**: ✅ Существует (legacy)
- **Описание**: Существующий репозиторий RAG документов
- **Зависимости**: `models/rag.py`

---

## Этап 4: Сервисы (Business Logic Layer)

### 4.1 Базовые сервисы

#### `apps/api/src/app/services/_base.py`
- **Статус**: ✅ Готово
- **Описание**: Базовый сервис с общим функционалом и валидацией
- **Зависимости**: `repositories/`, `logging.py`
- **Интерфейс**:
  ```python
  class BaseService:
      def _validate_required_fields(self, data: dict, required: list) -> None
      def _sanitize_string(self, value: str, max_length: int) -> str
      def _validate_email(self, email: str) -> bool
      def _validate_uuid(self, value: str) -> bool
      def _log_operation(self, operation: str, entity_id: str) -> None
      def _handle_error(self, operation: str, error: Exception, context: dict) -> None
  ```

### 4.2 Сервисы аутентификации

#### `apps/api/src/app/services/auth_service.py`
- **Статус**: ⏳ Планируется
- **Описание**: Сервис аутентификации
- **Зависимости**: `users_repo.py`, `security.py`
- **Интерфейс**:
  ```python
  class AuthService:
      async def authenticate_user(self, login: str, password: str) -> Optional[Users]
      async def create_access_token(self, user: Users) -> str
      async def verify_token(self, token: str) -> Optional[Users]
      async def refresh_token(self, refresh_token: str) -> Optional[str]
  ```

#### `apps/api/src/app/services/admin_service.py`
- **Статус**: ⏳ Планируется
- **Описание**: Административные функции
- **Зависимости**: `users_repo.py`, `auth_service.py`
- **Интерфейс**:
  ```python
  class AdminService:
      async def create_user(self, user_data: dict) -> Users
      async def update_user_role(self, user_id: UUID, role: str) -> bool
      async def deactivate_user(self, user_id: UUID) -> bool
  ```

### 4.3 Сервисы пользователей

#### `apps/api/src/app/services/users_service_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Расширенный сервис управления пользователями с полным функционалом
- **Зависимости**: `_base.py`, `repositories/users_repo_enhanced.py`, `bcrypt`
- **Интерфейс**:
  ```python
  class UsersService(RepositoryService[Users]):
      def create_user(self, login: str, password: str, role: str = "reader", email: Optional[str] = None, is_active: bool = True) -> Users
      def authenticate_user(self, login: str, password: str) -> Optional[Users]
      def change_password(self, user_id: str, old_password: str, new_password: str) -> bool
      def reset_password_request(self, email: str) -> bool
      def reset_password_confirm(self, token: str, new_password: str) -> bool
      def create_pat_token(self, user_id: str, name: str, scopes: Optional[List[str]] = None, expires_at: Optional[datetime] = None) -> Tuple[UserTokens, str]
      def revoke_pat_token(self, user_id: str, token_id: str) -> bool
      def search_users(self, query: str, role: Optional[str] = None, is_active: Optional[bool] = None, limit: int = 50) -> List[Users]
      def get_user_stats(self, user_id: str) -> Dict[str, Any]
  ```

#### `apps/api/src/app/services/users_service.py`
- **Статус**: ✅ Существует (legacy)
- **Описание**: Управление пользователями
- **Зависимости**: `users_repo.py`
- **Интерфейс**:
  ```python
  class UsersService:
      async def get_user_profile(self, user_id: UUID) -> Optional[dict]
      async def update_user_profile(self, user_id: UUID, data: dict) -> bool
      async def change_password(self, user_id: UUID, old_password: str, new_password: str) -> bool
  ```

### 4.4 Сервисы чатов

#### `apps/api/src/app/services/chats_service.py`
- **Статус**: ⏳ Планируется
- **Описание**: Управление чатами
- **Зависимости**: `chats_repo.py`, `llm_service`
- **Интерфейс**:
  ```python
  class ChatsService:
      async def create_chat(self, user_id: UUID, name: str) -> Chats
      async def send_message(self, chat_id: UUID, message: dict) -> ChatMessages
      async def get_chat_history(self, chat_id: UUID) -> List[ChatMessages]
  ```

### 4.5 RAG сервисы

#### `apps/api/src/app/services/rag_service.py`
- **Статус**: ⏳ Планируется
- **Описание**: RAG функциональность
- **Зависимости**: `rag_repo.py`, `emb_service`, `qdrant`
- **Интерфейс**:
  ```python
  class RAGService:
      async def upload_document(self, file: UploadFile, user_id: str) -> RAGDocument
      async def search_documents(self, query: str, user_id: str) -> List[dict]
      async def process_document(self, document_id: str) -> bool
  ```

---

## Этап 5: API слой

### 5.1 Базовые компоненты API

#### `apps/api/src/app/api/controllers/_base.py`
- **Статус**: ✅ Готово
- **Описание**: Базовый контроллер с общим функционалом
- **Зависимости**: `services/`, `schemas/`
- **Интерфейс**:
  ```python
  class BaseController:
      def _generate_request_id(self) -> str
      def _extract_user_info(self, current_user: Dict[str, Any]) -> Dict[str, Any]
      def _validate_uuid_param(self, value: str, param_name: str) -> None
      def _validate_pagination_params(self, limit: int, offset: int) -> None
      def _create_success_response(self, data: Any, message: str = None, request_id: str = None) -> Dict[str, Any]
      def _create_error_response(self, code: str, message: str, details: Dict[str, Any] = None, request_id: str = None) -> Dict[str, Any]
      def _handle_controller_error(self, operation: str, error: Exception, request_id: str = None) -> HTTPException
      def _log_api_operation(self, operation: str, user_info: Dict[str, Any], request_id: str, context: Dict[str, Any] = None) -> None
  ```

### 5.2 Схемы API

#### `apps/api/src/app/api/schemas/users.py`
- **Статус**: ✅ Готово
- **Описание**: Pydantic схемы для пользователей
- **Зависимости**: `pydantic`
- **Интерфейс**:
  ```python
  class UserCreateRequest(BaseModel)
  class UserUpdateRequest(BaseModel)
  class UserResponse(BaseModel)
  class UserListResponse(BaseModel)
  class TokenCreateRequest(BaseModel)
  class TokenResponse(BaseModel)
  ```

#### `apps/api/src/app/api/schemas/chats.py`
- **Статус**: ✅ Готово
- **Описание**: Pydantic схемы для чатов
- **Зависимости**: `pydantic`
- **Интерфейс**:
  ```python
  class ChatCreateRequest(BaseModel)
  class ChatUpdateRequest(BaseModel)
  class ChatResponse(BaseModel)
  class ChatMessageCreateRequest(BaseModel)
  class ChatMessageResponse(BaseModel)
  ```

#### `apps/api/src/app/api/schemas/rag.py`
- **Статус**: ✅ Готово
- **Описание**: Pydantic схемы для RAG
- **Зависимости**: `pydantic`
- **Интерфейс**:
  ```python
  class RAGDocumentUploadRequest(BaseModel)
  class RAGDocumentResponse(BaseModel)
  class RAGChunkCreateRequest(BaseModel)
  class RAGChunkResponse(BaseModel)
  ```

### 5.3 Контроллеры

#### `apps/api/src/app/api/controllers/users.py`
- **Статус**: ✅ Готово
- **Описание**: Контроллер для управления пользователями
- **Зависимости**: `_base.py`, `services/users_service_enhanced.py`, `schemas/users.py`
- **Интерфейс**:
  ```python
  class UsersController:
      async def create_user(self, request: UserCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def get_user(self, user_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def update_user(self, user_id: str, request: UserUpdateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def search_users(self, request: UserSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
  ```

#### `apps/api/src/app/api/controllers/chats.py`
- **Статус**: ✅ Готово
- **Описание**: Контроллеры для управления чатами и сообщениями
- **Зависимости**: `_base.py`, `services/chats_service_enhanced.py`, `schemas/chats.py`
- **Интерфейс**:
  ```python
  class ChatsController:
      async def create_chat(self, request: ChatCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def get_chat(self, chat_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def update_chat(self, chat_id: str, request: ChatUpdateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def get_user_chats(self, request: ChatSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
  
  class ChatMessagesController:
      async def create_message(self, chat_id: str, request: ChatMessageCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def get_chat_messages(self, chat_id: str, request: ChatMessagesListRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
  ```

#### `apps/api/src/app/api/controllers/rag.py`
- **Статус**: ✅ Готово
- **Описание**: Контроллеры для управления RAG документами и чанками
- **Зависимости**: `_base.py`, `services/rag_service_enhanced.py`, `schemas/rag.py`
- **Интерфейс**:
  ```python
  class RAGDocumentsController:
      async def create_document(self, request: RAGDocumentCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def get_document(self, document_id: str, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def search_documents(self, request: RAGDocumentSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
  
  class RAGChunksController:
      async def create_chunk(self, document_id: str, request: RAGChunkCreateRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def get_document_chunks(self, document_id: str, limit: int, current_user: Dict[str, Any]) -> Dict[str, Any]
      async def search_chunks(self, document_id: str, request: RAGChunkSearchRequest, current_user: Dict[str, Any]) -> Dict[str, Any]
  ```

### 5.4 Тесты контроллеров

#### `apps/api/tests/test_controllers_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Тесты для всех контроллеров
- **Покрытие**: 20 тестов для всех контроллеров
- **Результат**: Все тесты проходят успешно

### 5.5 Зависимости FastAPI

#### `apps/api/src/app/api/deps.py`
- **Статус**: ⏳ Планируется
- **Описание**: Зависимости FastAPI
- **Зависимости**: `auth_service.py`, `db.py`
- **Интерфейс**:
  ```python
  async def get_current_user(token: str = Depends(oauth2_scheme)) -> Users
  async def get_db_session() -> AsyncSession
  async def get_current_active_user(user: Users = Depends(get_current_user)) -> Users
  ```

### 5.6 Роутеры

#### `apps/api/src/app/api/routers/auth.py`
- **Статус**: ⏳ Планируется
- **Описание**: Аутентификация API
- **Зависимости**: `auth_service.py`, `schemas/auth.py`
- **Интерфейс**:
  ```python
  @router.post("/login")
  async def login(credentials: LoginRequest) -> LoginResponse
  
  @router.post("/refresh")
  async def refresh_token(refresh_data: RefreshRequest) -> TokenResponse
  ```

#### `apps/api/src/app/api/routers/chats.py`
- **Статус**: ⏳ Планируется
- **Описание**: Чаты API
- **Зависимости**: `chats_service.py`, `schemas/chats.py`
- **Интерфейс**:
  ```python
  @router.post("/")
  async def create_chat(chat_data: CreateChatRequest) -> ChatResponse
  
  @router.get("/{chat_id}/messages")
  async def get_messages(chat_id: UUID) -> List[MessageResponse]
  ```

---

## Этап 6: Фоновые задачи ✅ ЗАВЕРШЕН

### 6.1 Celery настройка ✅

#### `apps/api/src/app/celery_app.py`
- **Статус**: ✅ Готово
- **Описание**: Celery приложение с очередями и маршрутизацией
- **Зависимости**: `config.py`, `redis.py`
- **Интерфейс**:
  ```python
  app = Celery("backend", broker=BROKER_URL, backend=RESULT_BACKEND)
  # Настройка очередей с приоритетами
  # Маршрутизация задач по очередям
  ```

### 6.2 Улучшенные фоновые задачи ✅

#### `apps/api/src/app/tasks/bg_tasks_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Улучшенные фоновые задачи с интеграцией новых сервисов
- **Зависимости**: `celery_app.py`, `rag_service_enhanced.py`, `s3_manager`, `redis_manager`
- **Интерфейс**:
  ```python
  @shared_task(name="bg_tasks.process_document")
  def process_document(document_id: str, source_key: Optional[str] = None) -> Dict[str, Any]
  
  @shared_task(name="bg_tasks.extract_and_normalize_text")
  def extract_and_normalize_text(document_id: str, source_key: Optional[str] = None) -> Dict[str, Any]
  
  @shared_task(name="bg_tasks.chunk_document")
  def chunk_document(document_id: str, text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> Dict[str, Any]
  
  @shared_task(name="bg_tasks.generate_embeddings")
  def generate_embeddings(document_id: str, model: str = "minilm", batch_size: int = 8) -> Dict[str, Any]
  
  @shared_task(name="bg_tasks.finalize_document")
  def finalize_document(document_id: str) -> Dict[str, Any]
  
  @shared_task(name="bg_tasks.analyze_document")
  def analyze_document(document_id: str, analysis_type: str = "summary") -> Dict[str, Any]
  
  @shared_task(name="bg_tasks.cleanup_old_documents")
  def cleanup_old_documents(days_old: int = 30) -> Dict[str, Any]
  ```

### 6.3 Менеджер задач ✅

#### `apps/api/src/app/tasks/task_manager.py`
- **Статус**: ✅ Готово
- **Описание**: Менеджер для управления фоновыми задачами
- **Зависимости**: `celery_app.py`, `redis_manager`, `rag_service_enhanced.py`
- **Интерфейс**:
  ```python
  class TaskManager:
      async def process_document_async(self, document_id: str, source_key: Optional[str] = None, priority: str = "normal") -> Dict[str, Any]
      async def analyze_document_async(self, document_id: str, analysis_type: str = "summary", priority: str = "normal") -> Dict[str, Any]
      async def cleanup_old_documents_async(self, days_old: int = 30, priority: str = "low") -> Dict[str, Any]
      async def get_task_status(self, task_id: str) -> Dict[str, Any]
      async def get_document_tasks(self, document_id: str) -> List[Dict[str, Any]]
      async def cancel_task(self, task_id: str) -> bool
      async def schedule_document_processing(self, document_ids: List[str], priority: str = "normal", delay_seconds: int = 0) -> List[Dict[str, Any]]
      async def get_queue_stats(self) -> Dict[str, Any]
      async def get_worker_stats(self) -> Dict[str, Any]
  ```

### 6.4 Периодические задачи ✅

#### `apps/api/src/app/tasks/periodic_tasks.py`
- **Статус**: ✅ Готово
- **Описание**: Периодические задачи, выполняемые по расписанию
- **Зависимости**: `celery_app.py`, `bg_tasks_enhanced.py`, `task_manager.py`
- **Интерфейс**:
  ```python
  @shared_task(name="periodic_tasks.cleanup_old_documents_daily")
  def cleanup_old_documents_daily() -> Dict[str, Any]
  
  @shared_task(name="periodic_tasks.system_health_check")
  def system_health_check() -> Dict[str, Any]
  
  @shared_task(name="periodic_tasks.update_system_statistics")
  def update_system_statistics() -> Dict[str, Any]
  
  @shared_task(name="periodic_tasks.cleanup_temp_files")
  def cleanup_temp_files() -> Dict[str, Any]
  
  @shared_task(name="periodic_tasks.reindex_failed_documents")
  def reindex_failed_documents() -> Dict[str, Any]
  
  @shared_task(name="periodic_tasks.monitor_queue_health")
  def monitor_queue_health() -> Dict[str, Any]
  ```

### 6.5 Тесты фоновых задач ✅

#### `apps/api/tests/test_bg_tasks_enhanced.py`
- **Статус**: ✅ Готово
- **Описание**: Тесты для всех фоновых задач
- **Покрытие**: 17 тестов для всех компонентов
- **Результат**: Все тесты проходят успешно

---

## Скрипты проверки

### 8.1 Главный скрипт проверки ✅
#### `apps/api/full_check.py`
- **Статус**: ✅ Готово
- **Описание**: Главный скрипт для полной проверки системы
- **Зависимости**: `subprocess`, `sys`, `os`, `time`
- **Интерфейс**:
  ```python
  # Запуск всех проверок
  # Статистика выполнения
  # Итоговый отчет
  ```

### 8.2 Скрипт тестирования ✅
#### `apps/api/run_all_tests.py`
- **Статус**: ✅ Готово
- **Описание**: Запуск всех тестов системы
- **Зависимости**: `subprocess`, `sys`, `os`
- **Интерфейс**:
  ```python
  # 141 тест (все компоненты)
  # Группировка по типам
  # Детальная статистика
  ```

### 8.3 Скрипт проверки линтеров ✅
#### `apps/api/check_linters.py`
- **Статус**: ✅ Готово
- **Описание**: Проверка синтаксиса и импортов
- **Зависимости**: `subprocess`, `sys`, `os`
- **Интерфейс**:
  ```python
  # Проверка синтаксиса Python
  # Проверка импортов
  # Проверка циклических зависимостей
  ```

### 8.4 Скрипт проверки производительности ✅
#### `apps/api/check_performance.py`
- **Статус**: ✅ Готово
- **Описание**: Тестирование производительности всех компонентов
- **Зависимости**: `asyncio`, `time`, `sys`, `os`
- **Интерфейс**:
  ```python
  # Тесты БД, Redis, S3
  # Тесты сервисов
  # Тесты API
  # Измерение времени выполнения
  ```

### 8.5 Скрипт проверки безопасности ✅
#### `apps/api/check_security.py`
- **Статус**: ✅ Готово
- **Описание**: Проверка безопасности системы
- **Зависимости**: `subprocess`, `sys`, `os`
- **Интерфейс**:
  ```python
  # Безопасность паролей
  # Безопасность JWT
  # Валидация входных данных
  # Защита от SQL инъекций
  # Безопасность файлов
  ```

### 8.6 Документация скриптов ✅
#### `apps/api/README_SCRIPTS.md`
- **Статус**: ✅ Готово
- **Описание**: Документация по всем скриптам проверки
- **Зависимости**: Markdown
- **Интерфейс**:
  ```markdown
  # Описание всех скриптов
  # Инструкции по использованию
  # Устранение неполадок
  # Автоматизация
  ```

---

## Этап 7: Интеграция

### 7.1 Главное приложение

#### `apps/api/src/app/main.py`
- **Статус**: ⏳ Планируется
- **Описание**: FastAPI приложение
- **Зависимости**: Все роутеры, middleware
- **Интерфейс**:
  ```python
  app = FastAPI(title="ML Portal API")
  app.include_router(auth_router)
  app.include_router(chats_router)
  # ... другие роутеры
  ```

---

## Общие принципы

### Именование
- **Файлы**: snake_case
- **Классы**: PascalCase
- **Функции/методы**: snake_case
- **Константы**: UPPER_SNAKE_CASE

### Типизация
- Все функции должны иметь типы входных и выходных параметров
- Использовать `Optional` для nullable полей
- Использовать `List[T]` вместо `list[T]` для совместимости

### Обработка ошибок
- Использовать кастомные исключения
- Логировать все ошибки
- Возвращать понятные сообщения об ошибках

### Тестирование
- Покрытие тестами не менее 80%
- Unit тесты для каждого компонента
- Integration тесты для API
- E2E тесты для критических сценариев
