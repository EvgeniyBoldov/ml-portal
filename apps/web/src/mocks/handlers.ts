import { setupServer } from 'msw/node';
import { rest } from 'msw';

// Mock API responses
export const handlers = [
  // Auth endpoints
  rest.post('/api/v1/auth/login', (req, res, ctx) => {
    const { email, password } = req.body as any;
    
    if (email === 'test@example.com' && password === 'password123') {
      return res(
        ctx.json({
          access_token: 'mock-access-token',
          refresh_token: 'mock-refresh-token',
          token_type: 'Bearer',
          expires_in: 900
        })
      );
    }
    
    return res(
      ctx.status(401),
      ctx.json({ error: 'Invalid credentials' })
    );
  }),

  rest.post('/api/v1/auth/refresh', (req, res, ctx) => {
    return res(
      ctx.json({
        access_token: 'new-mock-access-token',
        refresh_token: 'new-mock-refresh-token',
        token_type: 'Bearer',
        expires_in: 900
      })
    );
  }),

  rest.get('/api/v1/auth/me', (req, res, ctx) => {
    const authHeader = req.headers.get('Authorization');
    
    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return res(
        ctx.status(401),
        ctx.json({ error: 'Unauthorized' })
      );
    }
    
    return res(
      ctx.json({
        id: '1',
        email: 'test@example.com',
        role: 'user',
        tenant_ids: ['tenant-1'],
        scopes: ['read', 'write']
      })
    );
  }),

  rest.get('/api/v1/auth/.well-known/jwks.json', (req, res, ctx) => {
    return res(
      ctx.json({
        keys: [
          {
            kty: 'oct',
            kid: 'mock-key-id',
            use: 'sig',
            alg: 'HS256',
            k: 'mock-secret-key'
          }
        ]
      })
    );
  }),

  // Chat endpoints
  rest.get('/api/v1/chats', (req, res, ctx) => {
    const tenantId = req.headers.get('X-Tenant-Id');
    
    if (!tenantId) {
      return res(
        ctx.status(400),
        ctx.json({ error: 'X-Tenant-Id header is required' })
      );
    }
    
    return res(
      ctx.json({
        items: [
          { id: '1', name: 'Test Chat 1', created_at: '2024-01-15T10:00:00Z' },
          { id: '2', name: 'Test Chat 2', created_at: '2024-01-15T11:00:00Z' }
        ],
        next_cursor: 'cursor-123',
        has_next: true
      })
    );
  }),

  rest.post('/api/v1/chats', (req, res, ctx) => {
    const tenantId = req.headers.get('X-Tenant-Id');
    const idempotencyKey = req.headers.get('Idempotency-Key');
    
    if (!tenantId) {
      return res(
        ctx.status(400),
        ctx.json({ error: 'X-Tenant-Id header is required' })
      );
    }
    
    if (!idempotencyKey) {
      return res(
        ctx.status(400),
        ctx.json({ error: 'Idempotency-Key header is required' })
      );
    }
    
    return res(
      ctx.status(201),
      ctx.json({
        id: 'new-chat-id',
        name: 'New Chat',
        created_at: new Date().toISOString()
      })
    );
  }),

  // RAG endpoints
  rest.get('/api/v1/rag/documents', (req, res, ctx) => {
    const tenantId = req.headers.get('X-Tenant-Id');
    
    if (!tenantId) {
      return res(
        ctx.status(400),
        ctx.json({ error: 'X-Tenant-Id header is required' })
      );
    }
    
    return res(
      ctx.json({
        items: [
          { id: '1', filename: 'document1.pdf', title: 'Document 1' },
          { id: '2', filename: 'document2.txt', title: 'Document 2' }
        ],
        next_cursor: 'doc-cursor-123',
        has_next: false
      })
    );
  }),

  rest.post('/api/v1/rag/documents', (req, res, ctx) => {
    const tenantId = req.headers.get('X-Tenant-Id');
    const idempotencyKey = req.headers.get('Idempotency-Key');
    
    if (!tenantId) {
      return res(
        ctx.status(400),
        ctx.json({ error: 'X-Tenant-Id header is required' })
      );
    }
    
    if (!idempotencyKey) {
      return res(
        ctx.status(400),
        ctx.json({ error: 'Idempotency-Key header is required' })
      );
    }
    
    return res(
      ctx.status(201),
      ctx.json({
        id: 'new-doc-id',
        filename: 'new-document.pdf',
        title: 'New Document',
        created_at: new Date().toISOString()
      })
    );
  }),

  // Health check
  rest.get('/api/v1/healthz', (req, res, ctx) => {
    return res(
      ctx.json({ status: 'ok' })
    );
  }),

  rest.get('/api/v1/readyz', (req, res, ctx) => {
    return res(
      ctx.json({ status: 'ok' })
    );
  })
];

// Error scenarios
export const errorHandlers = [
  rest.post('/api/v1/auth/login', (req, res, ctx) => {
    return res(
      ctx.status(500),
      ctx.json({ error: 'Internal server error' })
    );
  }),

  rest.get('/api/v1/chats', (req, res, ctx) => {
    return res(
      ctx.status(403),
      ctx.json({ error: 'Forbidden' })
    );
  })
];

// Network error scenarios
export const networkErrorHandlers = [
  rest.post('/api/v1/auth/login', (req, res, ctx) => {
    return res.networkError('Failed to connect');
  })
];

// Setup MSW server
export const server = setupServer(...handlers);

// Test data
export const testUsers = {
  admin: {
    id: '1',
    email: 'admin@example.com',
    role: 'admin',
    tenant_ids: ['tenant-1', 'tenant-2'],
    scopes: ['read', 'write', 'admin']
  },
  user: {
    id: '2',
    email: 'user@example.com',
    role: 'user',
    tenant_ids: ['tenant-1'],
    scopes: ['read', 'write']
  },
  reader: {
    id: '3',
    email: 'reader@example.com',
    role: 'reader',
    tenant_ids: ['tenant-1'],
    scopes: ['read']
  }
};

export const testChats = [
  {
    id: '1',
    name: 'Test Chat 1',
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
    tenant_id: 'tenant-1'
  },
  {
    id: '2',
    name: 'Test Chat 2',
    created_at: '2024-01-15T11:00:00Z',
    updated_at: '2024-01-15T11:00:00Z',
    tenant_id: 'tenant-1'
  }
];

export const testDocuments = [
  {
    id: '1',
    filename: 'document1.pdf',
    title: 'Document 1',
    content_type: 'application/pdf',
    size: 1024,
    created_at: '2024-01-15T10:00:00Z',
    tenant_id: 'tenant-1'
  },
  {
    id: '2',
    filename: 'document2.txt',
    title: 'Document 2',
    content_type: 'text/plain',
    size: 512,
    created_at: '2024-01-15T11:00:00Z',
    tenant_id: 'tenant-1'
  }
];
