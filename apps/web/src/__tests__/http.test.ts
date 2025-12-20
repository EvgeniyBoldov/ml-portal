import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  setAuthTokens,
  clearAuthTokens,
  getAccessToken,
  apiRequest,
} from '@shared/api/http';

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('HTTP Client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearAuthTokens();
  });

  afterEach(() => {
    clearAuthTokens();
  });

  describe('Auth Token Management', () => {
    it('should store access token', () => {
      setAuthTokens({ access_token: 'test-token-123' });
      expect(getAccessToken()).toBe('test-token-123');
    });

    it('should clear access token', () => {
      setAuthTokens({ access_token: 'test-token' });
      clearAuthTokens();
      expect(getAccessToken()).toBeNull();
    });

    it('should handle null tokens', () => {
      setAuthTokens({ access_token: 'test' });
      setAuthTokens(null);
      expect(getAccessToken()).toBeNull();
    });

    it('should handle empty access_token', () => {
      setAuthTokens({ access_token: '' });
      expect(getAccessToken()).toBeNull();
    });
  });

  describe('apiRequest()', () => {
    it('should make GET request', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ data: 'test' }),
      });

      const result = await apiRequest('/api/test');

      expect(mockFetch).toHaveBeenCalledTimes(1);
      expect(result).toEqual({ data: 'test' });
    });

    it('should include Authorization header when token is set', async () => {
      setAuthTokens({ access_token: 'bearer-token' });

      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test');

      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers.get('Authorization')).toBe('Bearer bearer-token');
    });

    it('should not include Authorization header when no token', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test');

      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers.get('Authorization')).toBeNull();
    });

    it('should add Idempotency-Key for POST requests', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test', { method: 'POST', body: JSON.stringify({}) });

      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers.get('Idempotency-Key')).toBeTruthy();
    });

    it('should add Idempotency-Key for PUT requests', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test', { method: 'PUT', body: JSON.stringify({}) });

      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers.get('Idempotency-Key')).toBeTruthy();
    });

    it('should not add Idempotency-Key for GET requests', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test', { method: 'GET' });

      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers.get('Idempotency-Key')).toBeNull();
    });

    it('should set Content-Type to application/json by default', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test');

      const [, options] = mockFetch.mock.calls[0];
      expect(options.headers.get('Content-Type')).toBe('application/json');
    });

    it('should not override Content-Type for FormData', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      const formData = new FormData();
      formData.append('file', new Blob(['test']));

      await apiRequest('/api/upload', { method: 'POST', body: formData });

      const [, options] = mockFetch.mock.calls[0];
      // FormData should not have Content-Type set (browser sets it with boundary)
      expect(options.headers.get('Content-Type')).toBeNull();
    });

    it('should include credentials', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({}),
      });

      await apiRequest('/api/test');

      const [, options] = mockFetch.mock.calls[0];
      expect(options.credentials).toBe('include');
    });

    it('should handle 204 No Content', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 204,
        headers: new Headers(),
      });

      const result = await apiRequest('/api/delete');

      expect(result).toBeUndefined();
    });

    it('should handle text response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'text/plain' }),
        text: async () => 'plain text response',
      });

      const result = await apiRequest('/api/text');

      expect(result).toBe('plain text response');
    });

    it('should throw ApiError for non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ detail: 'Bad request' }),
      });

      await expect(apiRequest('/api/test')).rejects.toThrow();
    });

    it('should retry on 401 with token refresh', async () => {
      setAuthTokens({ access_token: 'old-token' });

      // First call returns 401
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ detail: 'Unauthorized' }),
      });

      // Refresh call succeeds
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ access_token: 'new-token' }),
      });

      // Retry call succeeds
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ data: 'success' }),
      });

      const result = await apiRequest('/api/protected');

      expect(mockFetch).toHaveBeenCalledTimes(3);
      expect(result).toEqual({ data: 'success' });
      expect(getAccessToken()).toBe('new-token');
    });
  });
});
