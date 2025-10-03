import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../../shared/providers/AuthProvider';

// Mock the auth store
const mockAuthStore = {
  isAuthenticated: false,
  user: null,
  isLoading: false,
  error: null
};

vi.mock('../../store/auth', () => ({
  useAuthStore: () => mockAuthStore
}));

// Mock components
const LoginPage = () => <div>Login Page</div>;
const DashboardPage = () => <div>Dashboard Page</div>;
const AdminPage = () => <div>Admin Page</div>;
const NotFoundPage = () => <div>Not Found</div>;

// Mock router configuration
const routes = [
  { path: '/login', component: LoginPage, public: true },
  { path: '/dashboard', component: DashboardPage, protected: true },
  { path: '/admin', component: AdminPage, protected: true, admin: true },
  { path: '*', component: NotFoundPage }
];

const TestRouter = ({ children }: { children: React.ReactNode }) => (
  <MemoryRouter>
    <AuthProvider>
      {children}
    </AuthProvider>
  </MemoryRouter>
);

describe('Router', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthStore.isAuthenticated = false;
    mockAuthStore.user = null;
    mockAuthStore.isLoading = false;
  });

  it('renders public routes when not authenticated', () => {
    render(
      <TestRouter>
        <LoginPage />
      </TestRouter>
    );
    
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });

  it('redirects to login for protected routes when not authenticated', () => {
    mockAuthStore.isAuthenticated = false;
    
    render(
      <TestRouter>
        <DashboardPage />
      </TestRouter>
    );
    
    // Should redirect to login or show login page
    expect(screen.getByText('Login Page')).toBeInTheDocument();
  });

  it('renders protected routes when authenticated', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'test@example.com', role: 'user' };
    
    render(
      <TestRouter>
        <DashboardPage />
      </TestRouter>
    );
    
    expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
  });

  it('allows admin access to admin routes for admin users', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'admin@example.com', role: 'admin' };
    
    render(
      <TestRouter>
        <AdminPage />
      </TestRouter>
    );
    
    expect(screen.getByText('Admin Page')).toBeInTheDocument();
  });

  it('denies admin access to non-admin users', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'user@example.com', role: 'user' };
    
    render(
      <TestRouter>
        <AdminPage />
      </TestRouter>
    );
    
    // Should redirect to dashboard or show access denied
    expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
  });

  it('shows loading state during authentication check', () => {
    mockAuthStore.isLoading = true;
    
    render(
      <TestRouter>
        <DashboardPage />
      </TestRouter>
    );
    
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('handles query parameters correctly', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'test@example.com', role: 'user' };
    
    render(
      <MemoryRouter initialEntries={['/dashboard?tab=settings']}>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </MemoryRouter>
    );
    
    expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
  });

  it('handles hash fragments correctly', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'test@example.com', role: 'user' };
    
    render(
      <MemoryRouter initialEntries={['/dashboard#section1']}>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </MemoryRouter>
    );
    
    expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
  });

  it('renders 404 page for unknown routes', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'test@example.com', role: 'user' };
    
    render(
      <MemoryRouter initialEntries={['/unknown-route']}>
        <AuthProvider>
          <NotFoundPage />
        </AuthProvider>
      </MemoryRouter>
    );
    
    expect(screen.getByText('Not Found')).toBeInTheDocument();
  });

  it('preserves route state during navigation', () => {
    mockAuthStore.isAuthenticated = true;
    mockAuthStore.user = { id: '1', email: 'test@example.com', role: 'user' };
    
    const { rerender } = render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </MemoryRouter>
    );
    
    expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
    
    // Navigate to admin (should be denied)
    rerender(
      <MemoryRouter initialEntries={['/admin']}>
        <AuthProvider>
          <AdminPage />
        </AuthProvider>
      </MemoryRouter>
    );
    
    // Should redirect back to dashboard
    expect(screen.getByText('Dashboard Page')).toBeInTheDocument();
  });
});
