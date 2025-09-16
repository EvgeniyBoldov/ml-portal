import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';
import { useAuthStore } from '../auth.store';

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
});

describe('useAuthStore', () => {
  beforeEach(() => {
    localStorageMock.getItem.mockClear();
    localStorageMock.setItem.mockClear();
    localStorageMock.removeItem.mockClear();
  });

  it('should initialize with empty state', () => {
    const { result } = renderHook(() => useAuthStore());

    expect(result.current.user).toBeNull();
    expect(result.current.tokens).toBeNull();
    expect(result.current.isAuthReady).toBe(false);
  });

  it('should login user', async () => {
    const { result } = renderHook(() => useAuthStore());

    const mockUser = { id: '1', login: 'test', role: 'admin' };
    const mockResponse = {
      access_token: 'token',
      token_type: 'Bearer',
      refresh_token: 'refresh_token',
      expires_in: 3600,
      user: mockUser,
    };

    // Mock fetch
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: () => Promise.resolve(mockResponse),
    });

    await act(async () => {
      await result.current.login('test', 'password');
    });

    expect(result.current.user).toEqual(mockUser);
    expect(result.current.tokens).toBeTruthy();
  });

  it('should logout user', async () => {
    const { result } = renderHook(() => useAuthStore());

    // First login
    const mockUser = { id: '1', login: 'test', role: 'admin' };
    const mockResponse = {
      access_token: 'token',
      token_type: 'Bearer',
      refresh_token: 'refresh_token',
      expires_in: 3600,
      user: mockUser,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: () => Promise.resolve(mockResponse),
    });

    await act(async () => {
      await result.current.login('test', 'password');
    });

    expect(result.current.tokens).toBeTruthy();

    // Then logout
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
    });

    await act(async () => {
      await result.current.logout();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.tokens).toBeNull();
  });

  it('should handle login errors', async () => {
    const { result } = renderHook(() => useAuthStore());

    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: () => Promise.resolve({ message: 'Invalid credentials' }),
    });

    await act(async () => {
      await expect(result.current.login('test', 'wrong')).rejects.toThrow();
    });

    expect(result.current.user).toBeNull();
    expect(result.current.tokens).toBeNull();
  });
});
