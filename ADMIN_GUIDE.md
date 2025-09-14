# ML Portal - Admin Guide

## Overview

This guide covers the RBAC (Role-Based Access Control) system and admin functionality implemented in the ML Portal backend.

## Features

### ✅ Implemented

- **RBAC System**: Three roles (admin, editor, reader) with proper access controls
- **Admin API**: Full CRUD operations for user management
- **PAT Tokens**: Personal Access Tokens with scopes and expiration
- **Password Reset**: Email-based password reset (optional)
- **Audit Logging**: Comprehensive audit trail for all admin actions
- **Security**: Rate limiting, password policies, secure token handling
- **CLI Tools**: Command-line utilities for superuser creation

### 🔄 Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   API Gateway   │    │   Backend       │
│                 │    │                 │    │                 │
│ - Login/Logout  │───▶│ - CORS          │───▶│ - RBAC          │
│ - User Mgmt     │    │ - Rate Limiting │    │ - Admin API     │
│ - Token Mgmt    │    │ - Security      │    │ - Audit Logs    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Roles and Permissions

### Admin Role
- **Full Access**: All operations including user management
- **Admin API**: Create, read, update, delete users
- **Token Management**: Create and revoke PAT tokens
- **Audit Access**: View all audit logs
- **System Management**: All RAG operations

### Editor Role
- **Content Management**: Upload, modify, delete RAG documents
- **Search**: Full access to RAG search functionality
- **Own Resources**: Can manage their own content
- **No Admin Access**: Cannot manage users or system settings

### Reader Role
- **Read-Only Access**: View RAG documents and search
- **No Upload**: Cannot upload or modify content
- **No Admin Access**: Cannot access admin functions

## API Endpoints

### Authentication
```
POST /api/auth/login          # Login with credentials
POST /api/auth/refresh        # Refresh access token
POST /api/auth/logout         # Logout and revoke tokens
GET  /api/auth/me             # Get current user info
```

### Password Reset (Optional)
```
POST /auth/password/forgot    # Request password reset
POST /auth/password/reset     # Reset password with token
```

### Admin API (Admin Only)
```
# User Management
GET    /api/admin/users                    # List users with pagination
POST   /api/admin/users                    # Create new user
GET    /api/admin/users/{id}               # Get user details
PATCH  /api/admin/users/{id}               # Update user
DELETE /api/admin/users/{id}               # Deactivate user
POST   /api/admin/users/{id}/password      # Reset user password

# Token Management
GET    /api/admin/users/{id}/tokens        # List user tokens
POST   /api/admin/users/{id}/tokens        # Create PAT token
DELETE /api/admin/tokens/{id}              # Revoke token

# Audit Logs
GET    /api/admin/audit-logs               # List audit logs
```

### RAG API (Role-Based)
```
# Read Operations (Reader+)
GET    /api/rag/                          # List documents
GET    /api/rag/{id}                      # Get document
GET    /api/rag/{id}/download             # Download document
GET    /api/rag/{id}/progress             # Get processing progress
GET    /api/rag/stats                     # Get statistics
POST   /api/rag/search                    # Search documents

# Write Operations (Editor+)
POST   /api/rag/upload                    # Upload document
POST   /api/rag/{id}/archive              # Archive document
PUT    /api/rag/{id}/tags                 # Update tags
DELETE /api/rag/{id}                      # Delete document
POST   /api/rag/{id}/reindex              # Reindex document
POST   /api/rag/reindex                   # Reindex all documents
```

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    login VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) CHECK (role IN ('admin', 'editor', 'reader')),
    is_active BOOLEAN DEFAULT TRUE,
    email VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### User Tokens Table (PAT)
```sql
CREATE TABLE user_tokens (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    name VARCHAR(255),
    scopes JSON,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE,
    revoked_at TIMESTAMP WITH TIME ZONE
);
```

### Password Reset Tokens
```sql
CREATE TABLE password_reset_tokens (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Audit Logs
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    ts TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(50) NOT NULL,
    object_type VARCHAR(50),
    object_id VARCHAR(255),
    meta JSON,
    ip VARCHAR(45),
    user_agent TEXT,
    request_id VARCHAR(255)
);
```

## Configuration

### Environment Variables

```bash
# Authentication
JWT_SECRET=your-secret-key
ACCESS_TTL_SECONDS=900
REFRESH_TTL_DAYS=7

# Email (Optional)
EMAIL_ENABLED=false
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
FROM_EMAIL=noreply@ml-portal.local

# Password Policy
PASSWORD_MIN_LENGTH=12
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGITS=true
PASSWORD_REQUIRE_SPECIAL=true

# Rate Limiting
RATE_LIMIT_LOGIN_ATTEMPTS=10
RATE_LIMIT_LOGIN_WINDOW=60
```

## Setup and Usage

### 1. Run Migrations
```bash
cd backend
python -m alembic upgrade head
```

### 2. Create Superuser
```bash
# Using CLI
python -m app.cli create-superuser --login admin --password 'secure_password123' --email admin@company.com

# Or using script
python scripts/create_superuser.py --login admin --password 'secure_password123' --email admin@company.com
```

### 3. Start the Application
```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 4. Access Admin Interface
- Login at `POST /api/auth/login`
- Use admin credentials
- Access admin API at `/api/admin/*`

## Security Features

### Password Security
- **Argon2id** hashing with salt
- **Minimum 12 characters** (configurable)
- **Complexity requirements** (configurable)
- **Password rotation** on admin reset

### Token Security
- **Short-lived access tokens** (15 minutes)
- **Refresh token rotation** (one-time use)
- **PAT token scoping** (granular permissions)
- **Token revocation** on password reset

### Rate Limiting
- **Login attempts**: 10 per minute per IP
- **API calls**: Configurable per endpoint
- **Brute force protection**

### Audit Trail
- **All admin actions** logged
- **User authentication** events
- **Token operations** tracked
- **IP and User-Agent** recording

## Testing

### Run Tests
```bash
# All tests
pytest

# RBAC tests only
pytest tests/test_rbac.py

# Admin API tests
pytest tests/test_admin.py
```

### Test Coverage
- ✅ Role-based access control
- ✅ Admin API CRUD operations
- ✅ Token management
- ✅ Password reset flow
- ✅ Audit logging
- ✅ Security policies

## Troubleshooting

### Common Issues

1. **Migration Errors**
   ```bash
   # Check current migration status
   python -m alembic current
   
   # Reset migrations (development only)
   python -m alembic downgrade base
   python -m alembic upgrade head
   ```

2. **Authentication Issues**
   ```bash
   # Check JWT secret
   echo $JWT_SECRET
   
   # Verify user exists
   python -c "from app.repositories.users_repo import UsersRepo; from app.core.db import get_session; repo = UsersRepo(next(get_session())); print(repo.by_login('admin'))"
   ```

3. **Permission Denied**
   - Check user role in database
   - Verify token is valid and not expired
   - Check audit logs for failed attempts

### Logs and Monitoring

- **Application logs**: JSON format with request IDs
- **Audit logs**: Available via admin API
- **Metrics**: Prometheus endpoint at `/metrics`
- **Health checks**: `/health` and `/healthz`

## API Examples

### Create User
```bash
curl -X POST "http://localhost:8000/api/admin/users" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "login": "newuser",
    "password": "secure_password123",
    "role": "editor",
    "email": "user@company.com"
  }'
```

### Create PAT Token
```bash
curl -X POST "http://localhost:8000/api/admin/users/USER_ID/tokens" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API Token",
    "scopes": ["api:read", "rag:read"],
    "expires_at": "2025-12-31T23:59:59Z"
  }'
```

### Search RAG Documents
```bash
curl -X POST "http://localhost:8000/api/rag/search" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning",
    "top_k": 10,
    "min_score": 0.7
  }'
```

## Future Enhancements

- [ ] **Email Integration**: SMTP configuration for password reset
- [ ] **Advanced RBAC**: Resource-level permissions
- [ ] **SSO Integration**: LDAP/SAML support
- [ ] **Admin UI**: Web interface for user management
- [ ] **Bulk Operations**: Mass user import/export
- [ ] **Advanced Audit**: Real-time monitoring dashboard
- [ ] **Policy Engine**: Casbin/Oso integration
- [ ] **Multi-tenancy**: Organization-based access control
