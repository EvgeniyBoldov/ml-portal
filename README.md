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
   docker compose up -d
   ```

3. **Access the application**
   - Frontend: http://localhost:8080
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

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

#### Update Chat Tags
```bash
PUT /api/chats/{chat_id}/tags
{
  "tags": ["updated", "tags"]
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

#### List Documents
```bash
GET /api/rag/?page=1&size=20&status=ready&search=keyword
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
DATABASE_URL=postgresql://user:password@localhost/ml_portal
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
QDRANT_URL=http://localhost:6333
LLM_URL=http://localhost:8001
SECRET_KEY=your-secret-key
```

#### Frontend
```env
VITE_API_URL=http://localhost:8000
VITE_USE_MOCKS=false
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

## 🚀 Deployment

### Production Deployment

1. **Environment Setup**
   ```bash
   export DATABASE_URL=postgresql://prod_user:password@prod_host/ml_portal
   export REDIS_URL=redis://prod_redis:6379/0
   export SECRET_KEY=your-production-secret-key
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
