# ML Portal - AI-Powered Document Management System

A comprehensive AI-powered platform for document management, chat interactions, and knowledge base operations built with FastAPI, React, and modern AI technologies.

## 🚀 Features

### Core Functionality
- **💬 Intelligent Chat System**: Real-time chat with AI assistant using streaming responses
- **📚 RAG Document Management**: Upload, process, and search through documents using Retrieval Augmented Generation
- **📊 Document Analysis**: Upload and analyze documents with AI-powered insights
- **🏷️ Tagging System**: Organize chats and documents with custom tags
- **🔍 Advanced Search**: Semantic search across document collections
- **📈 Analytics & Metrics**: Comprehensive statistics and usage analytics
- **🤖 Advanced Embedding System**: Scalable embedding dispatcher with model registry and MinIO caching
- **📦 Model Management**: Download and manage ML models from HuggingFace

### Admin Panel
- **👥 User Management**: Create, edit, and manage users with RBAC
- **🔑 Token Management**: Personal Access Tokens (PAT) with flexible scopes
- **📋 Audit Logging**: Comprehensive audit trail of all system actions
- **⚙️ System Settings**: Email configuration and system monitoring
- **🔐 Role-Based Access Control**: Admin, Editor, Reader roles with proper permissions

### Technical Features
- **🌙 Dark/Light Theme**: Automatic theme detection with manual override
- **📱 Responsive Design**: Mobile-first responsive interface
- **♿ Accessibility**: ARIA attributes and keyboard navigation support
- **⚡ Performance**: Optimized with React.memo, useMemo, and caching
- **🔄 Real-time Updates**: WebSocket and Server-Sent Events for live updates
- **📦 Export/Import**: Multiple format support (JSON, TXT, Markdown)

## 🏗️ Architecture

### Backend (FastAPI)
```
backend/
├── app/
│   ├── api/                 # API routes and endpoints
│   │   ├── routers/         # Route handlers
│   │   └── deps.py          # Dependencies
│   ├── core/                # Core configuration
│   │   ├── config.py        # Settings and configuration
│   │   ├── db.py            # Database connection
│   │   ├── logging.py       # Structured logging
│   │   └── cache.py         # Redis caching
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic validation schemas
│   ├── services/            # Business logic
│   ├── repositories/        # Data access layer
│   └── tasks/               # Celery background tasks
├── tests/                   # Unit and integration tests
└── requirements.txt         # Python dependencies
```

### Frontend (React + TypeScript)
```
frontend/
├── src/
│   ├── app/                 # Application code
│   │   ├── components/      # Reusable components
│   │   ├── contexts/        # React contexts
│   │   ├── store/           # State management (Zustand)
│   │   └── routes/          # Page components
│   │       └── admin/       # Admin panel pages
│   ├── shared/              # Shared utilities
│   │   ├── api/             # API client
│   │   ├── ui/              # UI components
│   │   └── lib/             # Utility functions
│   └── theme.css            # CSS variables and theming
└── package.json             # Node.js dependencies
```

## 🛠️ Technology Stack

### Backend
- **FastAPI**: Modern, fast web framework for building APIs
- **PostgreSQL**: Primary database for structured data
- **Redis**: Caching and session storage
- **SQLAlchemy**: Python SQL toolkit and ORM
- **Alembic**: Database migration tool
- **Celery**: Distributed task queue
- **RabbitMQ**: Message broker for Celery
- **MinIO**: S3-compatible object storage
- **Qdrant**: Vector database for embeddings
- **Pydantic**: Data validation using Python type annotations

### Frontend
- **React 18**: Modern React with hooks and concurrent features
- **TypeScript**: Type-safe JavaScript
- **React Router**: Client-side routing
- **Zustand**: Lightweight state management
- **CSS Modules**: Scoped CSS styling
- **Vite**: Fast build tool and dev server

### AI/ML
- **Embeddings**: Text vectorization for semantic search
- **LLM Integration**: External AI service for chat responses
- **RAG Pipeline**: Document processing and retrieval system

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for local development)

### Using Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd ml-portal
   ```

2. **Start all services**
   ```bash
   make up
   ```

3. **Create admin user**
   ```bash
   make create-admin
   ```

4. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Admin Panel: http://localhost:3000/admin

### Local Development

1. **Backend Setup**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   pip install -r requirements-test.txt
   uvicorn app.main:app --reload
   ```

2. **Frontend Setup**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. **Database Setup**
   ```bash
   # Run migrations
   alembic upgrade head
   
   # Create admin user
   python scripts/create_admin_user.py
   ```

## 📖 API Documentation

### Authentication
All API endpoints require authentication via JWT tokens.

```bash
# Login
POST /api/auth/login
{
  "email": "admin@example.com",
  "password": "password"
}

# Response
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### Admin API

#### User Management
```bash
# List users
GET /api/admin/users?query=john&role=admin&is_active=true&limit=20&cursor=abc123

# Create user
POST /api/admin/users
{
  "login": "john_doe",
  "email": "john@example.com",
  "role": "editor",
  "is_active": true,
  "send_email": true
}

# Update user
PATCH /api/admin/users/{user_id}
{
  "role": "admin",
  "is_active": false
}

# Reset password
POST /api/admin/users/{user_id}/password
{
  "require_change": true
}
```

#### Token Management
```bash
# List user tokens
GET /api/admin/users/{user_id}/tokens

# Create token
POST /api/admin/users/{user_id}/tokens
{
  "name": "API Token",
  "scopes": ["api:read", "api:write"],
  "expires_at": "2024-12-31T23:59:59Z"
}

# Revoke token
DELETE /api/admin/tokens/{token_id}
```

#### Audit Logs
```bash
# Get audit logs
GET /api/admin/audit-logs?actor_user_id=123&action=user_created&start_date=2024-01-01&limit=50
```

### Chats API

#### Create Chat
```bash
POST /api/chats
{
  "name": "My Chat",
  "tags": ["work", "important"]
}
```

#### Send Message
```bash
POST /api/chats/{chat_id}/messages
{
  "content": "Hello, AI!",
  "use_rag": false,
  "response_stream": true
}
```

### RAG Documents API

#### Upload Document
```bash
POST /api/rag/upload
Content-Type: multipart/form-data

file: [binary file]
tags: ["document", "important"]
```

#### Search Documents
```bash
POST /api/rag/search
{
  "text": "search query",
  "top_k": 10,
  "min_score": 0.5
}
```

## 🧪 Testing

### Backend Tests
```bash
cd backend
pytest tests/ -v --cov=app
```

### Frontend Tests
```bash
cd frontend
npm test
```

### Integration Tests
```bash
# Run full test suite with Docker
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

## 🔧 Configuration

### Environment Variables

#### Backend
```env
# Database
DATABASE_URL=postgresql://user:password@localhost/ml_portal

# Redis
REDIS_URL=redis://localhost:6379/0

# Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Vector Database
QDRANT_URL=http://localhost:6333

# AI Services
LLM_URL=http://localhost:8001

# Security
JWT_SECRET=your-jwt-secret
PASSWORD_PEPPER=your-password-pepper

# Email (optional)
EMAIL_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=user@example.com
SMTP_PASSWORD=password
SMTP_USE_TLS=true
FROM_EMAIL=noreply@example.com

# CORS
CORS_ENABLED=true
CORS_ORIGINS=http://localhost:3000,https://yourdomain.com
CORS_ALLOW_CREDENTIALS=true

# Permissions
ALLOW_READER_UPLOADS=false
```

#### Frontend
```env
VITE_API_URL=http://localhost:8000
VITE_USE_MOCKS=false
```

## 🚀 Deployment

### Production Deployment

1. **Environment Setup**
   ```bash
   export DATABASE_URL=postgresql://prod_user:password@prod_host/ml_portal
   export REDIS_URL=redis://prod_redis:6379/0
   export JWT_SECRET=your-production-secret-key
   export PASSWORD_PEPPER=your-production-pepper
   ```

2. **Database Migration**
   ```bash
   alembic upgrade head
   ```

3. **Start Services**
   ```bash
   docker compose -f docker-compose.prod.yml up -d
   ```

### Scaling
- **Horizontal Scaling**: Multiple API instances behind load balancer
- **Database**: Read replicas for read-heavy operations
- **Caching**: Redis cluster for distributed caching
- **Storage**: S3-compatible storage for file persistence

## 🛠️ Development Commands

### Quick Start
```bash
# Build and start all services
make build-local
make up-local

# Initialize models bucket
make init-models

# Download popular embedding models
make download-popular

# Test embedding system
make demo-embedding
```

### Code Generation
```bash
# Generate code files
make gen-backend    # Backend code in tests/legacy/back.txt
make gen-frontend   # Frontend code in tests/legacy/front.txt
make gen-all        # All code
make gen-docs       # Architecture documentation
```

### Model Management
```bash
# Download models from HuggingFace
make download-models      # Show usage examples
make download-model       # Download specific model (e.g., BAAI/bge-3m)
make list-models          # Show downloaded models

# Direct usage
python scripts/download_model.py BAAI/bge-3m --test --info
python scripts/download_models.py sentence-transformers/all-MiniLM-L6-v2 --test
python scripts/download_models.py intfloat/e5-large-v2 --include "*.safetensors"
```

### System Management
```bash
# Services
make up-local       # Start local stack
make down-local     # Stop local stack
make logs           # Show all logs
make status         # Show service status

# Embedding system
make test-embedding # Test embedding system
make demo-embedding # Demo embedding system
make logs-embedding # Show embedding worker logs
```

### Utilities
```bash
# Cleanup
make clean          # Clean images and volumes

# Testing
make test-local     # Run tests in containers
```

## 📊 Monitoring & Logging

### Structured Logging
The application uses structured JSON logging with the following format:
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "logger": "app.api.routers.chats",
  "message": "API call: POST /chats",
  "api_call": {
    "method": "POST",
    "endpoint": "/chats",
    "user_id": "user-123",
    "status_code": 200,
    "duration_ms": 45.2
  }
}
```

### Metrics
- **RAG Metrics**: `/api/rag/metrics` - Document and chunk statistics
- **Health Check**: `/health` - Service health status
- **Prometheus**: `/metrics` - Prometheus-compatible metrics
- **Admin Metrics**: `/api/admin/system/status` - System and user statistics

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines
- Follow PEP 8 for Python code
- Use TypeScript strict mode
- Write tests for new features
- Update documentation
- Follow conventional commits

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the [documentation](docs/)
- Review the [API documentation](http://localhost:8000/docs)

## 🗺️ Roadmap

### Upcoming Features
- [ ] **Multi-language Support**: Internationalization (i18n)
- [ ] **Advanced Analytics**: Usage dashboards and insights
- [ ] **Collaboration**: Real-time collaborative editing
- [ ] **Mobile App**: React Native mobile application
- [ ] **Plugin System**: Extensible plugin architecture
- [ ] **Advanced AI**: Custom model training and fine-tuning

### Performance Improvements
- [ ] **CDN Integration**: Static asset delivery
- [ ] **Database Optimization**: Query optimization and indexing
- [ ] **Caching Strategy**: Advanced caching patterns
- [ ] **Bundle Optimization**: Code splitting and lazy loading

---

**Built with ❤️ using modern web technologies**