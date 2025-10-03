import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useAuthStore } from '../../store/auth';

// Mock the API client
vi.mock('../../shared/api/auth', () => ({
  login: vi.fn(),
  logout: vi.fn(),
  refreshToken: vi.fn(),
  getCurrentUser: vi.fn()
}));

describe('Auth Store', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.getState().reset();
    vi.clearAllMocks();
  });

  it('initializes with correct default state', () => {
    const state = useAuthStore.getState();
    
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('handles successful login', async () => {
    const mockUser = { id: '1', email: 'test@example.com', role: 'user' };
    const mockTokens = { access_token: 'access', refresh_token: 'refresh' };
    
    vi.mocked(require('../../shared/api/auth').login).mockResolvedValue({
      user: mockUser,
      tokens: mockTokens
    });
    
    const { login } = useAuthStore.getState();
    
    await login({ email: 'test@example.com', password: 'password' });
    
    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('handles login failure', async () => {
    const errorMessage = 'Invalid credentials';
    vi.mocked(require('../../shared/api/auth').login).mockRejectedValue(
      new Error(errorMessage)
    );
    
    const { login } = useAuthStore.getState();
    
    await login({ email: 'test@example.com', password: 'wrong' });
    
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBe(errorMessage);
  });

  it('handles logout', async () => {
    // First login
    const mockUser = { id: '1', email: 'test@example.com', role: 'user' };
    const mockTokens = { access_token: 'access', refresh_token: 'refresh' };
    
    vi.mocked(require('../../shared/api/auth').login).mockResolvedValue({
      user: mockUser,
      tokens: mockTokens
    });
    
    const { login, logout } = useAuthStore.getState();
    await login({ email: 'test@example.com', password: 'password' });
    
    // Then logout
    vi.mocked(require('../../shared/api/auth').logout).mockResolvedValue(undefined);
    await logout();
    
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
    expect(state.error).toBeNull();
  });

  it('handles token refresh', async () => {
    const mockUser = { id: '1', email: 'test@example.com', role: 'user' };
    const mockTokens = { access_token: 'new_access', refresh_token: 'new_refresh' };
    
    vi.mocked(require('../../shared/api/auth').refreshToken).mockResolvedValue(mockTokens);
    vi.mocked(require('../../shared/api/auth').getCurrentUser).mockResolvedValue(mockUser);
    
    const { refreshAuth } = useAuthStore.getState();
    await refreshAuth();
    
    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
    expect(state.isLoading).toBe(false);
  });

  it('handles refresh failure', async () => {
    vi.mocked(require('../../shared/api/auth').refreshToken).mockRejectedValue(
      new Error('Refresh failed')
    );
    
    const { refreshAuth } = useAuthStore.getState();
    await refreshAuth();
    
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.error).toBe('Refresh failed');
  });

  it('sets loading state during async operations', async () => {
    let resolveLogin: (value: any) => void;
    const loginPromise = new Promise(resolve => {
      resolveLogin = resolve;
    });
    
    vi.mocked(require('../../shared/api/auth').login).mockReturnValue(loginPromise);
    
    const { login } = useAuthStore.getState();
    
    // Start login
    const loginPromise2 = login({ email: 'test@example.com', password: 'password' });
    
    // Check loading state
    expect(useAuthStore.getState().isLoading).toBe(true);
    
    // Resolve login
    resolveLogin!({ user: { id: '1' }, tokens: {} });
    await loginPromise2;
    
    // Check loading state is false
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('clears error when starting new operation', async () => {
    // First, set an error
    useAuthStore.setState({ error: 'Previous error' });
    
    const mockUser = { id: '1', email: 'test@example.com', role: 'user' };
    vi.mocked(require('../../shared/api/auth').login).mockResolvedValue({
      user: mockUser,
      tokens: {}
    });
    
    const { login } = useAuthStore.getState();
    await login({ email: 'test@example.com', password: 'password' });
    
    expect(useAuthStore.getState().error).toBeNull();
  });

  it('provides selectors for derived state', () => {
    const mockUser = { id: '1', email: 'test@example.com', role: 'user' };
    useAuthStore.setState({ user: mockUser, isAuthenticated: true });
    
    const state = useAuthStore.getState();
    expect(state.isAdmin).toBe(false);
    expect(state.isReader).toBe(true);
    expect(state.userEmail).toBe('test@example.com');
  });
});
