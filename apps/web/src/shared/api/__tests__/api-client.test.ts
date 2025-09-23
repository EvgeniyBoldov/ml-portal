import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as authApi from '../auth';
import * as chatsApi from '../chats';
import * as ragApi from '../rag';

// Mock fetch
global.fetch = vi.fn();

describe('API Client Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Auth API', () => {
    it('should login with correct credentials', async () => {
      const mockResponse = {
        access_token: 'mock-token',
        refresh_token: 'mock-refresh',
        token_type: 'bearer',
        user: {
          id: '1',
          email: 'test@example.com',
          name: 'Test User'
        }
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockResponse)
      });

      const result = await authApi.login('test@example.com', 'password123');
      
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/login'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ login: 'test@example.com', password: 'password123' })
        })
      );
    });

    it('should get current user', async () => {
      const mockUser = {
        id: '1',
        email: 'test@example.com',
        name: 'Test User',
        role: 'user'
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockUser)
      });

      const result = await authApi.me();
      
      expect(result).toEqual(mockUser);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/auth/me'),
        expect.objectContaining({ method: 'GET' })
      );
    });
  });

  describe('Chats API', () => {
    it('should list chats', async () => {
      const mockResponse = {
        items: [
          {
            id: '1',
            name: 'Test Chat',
            tags: ['test'],
            created_at: '2023-01-01T00:00:00Z'
          }
        ],
        next_cursor: null
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockResponse)
      });

      const result = await chatsApi.listChats();
      
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chats'),
        expect.any(Object)
      );
    });

    it('should create chat', async () => {
      const mockResponse = { chat_id: 'new-chat-id' };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockResponse)
      });

      const result = await chatsApi.createChat('New Chat', ['tag1']);
      
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chats'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ name: 'New Chat', tags: ['tag1'] })
        })
      );
    });

    it('should send message', async () => {
      const mockResponse = {
        id: 'msg-1',
        chat_id: 'chat-1',
        role: 'assistant',
        content: 'Hello!',
        created_at: '2023-01-01T00:00:00Z'
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockResponse)
      });

      const result = await chatsApi.sendMessage('chat-1', {
        content: 'Hello',
        use_rag: false
      });
      
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chats/chat-1/messages'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ content: 'Hello', use_rag: false })
        })
      );
    });
  });

  describe('RAG API', () => {
    it('should list documents', async () => {
      const mockResponse = {
        items: [
          {
            id: 'doc-1',
            title: 'Test Document',
            status: 'processed'
          }
        ],
        pagination: {
          page: 1,
          size: 10,
          total: 1,
          total_pages: 1,
          has_next: false,
          has_prev: false
        }
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockResponse)
      });

      const result = await ragApi.listDocs();
      
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/rag/'),
        expect.any(Object)
      );
    });

    it('should upload file', async () => {
      const mockResponse = {
        id: 'doc-1',
        status: 'processing'
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        headers: {
          get: (name: string) => name === 'Content-Type' ? 'application/json' : null
        },
        json: () => Promise.resolve(mockResponse)
      });

      const file = new File(['test content'], 'test.txt', { type: 'text/plain' });
      const result = await ragApi.uploadFile(file, 'Test Document', ['tag1']);
      
      expect(result).toEqual(mockResponse);
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/rag/upload'),
        expect.objectContaining({
          method: 'POST',
          body: expect.any(FormData)
        })
      );
    });
  });
});
