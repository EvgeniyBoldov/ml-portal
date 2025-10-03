import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Login } from '../../pages/Login';

// Mock the auth store
vi.mock('../../store/auth', () => ({
  useAuthStore: () => ({
    login: vi.fn(),
    isLoading: false,
    error: null
  })
}));

// Mock the router
vi.mock('../../router', () => ({
  useNavigate: () => vi.fn()
}));

describe('Login Form', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login form with required fields', () => {
    render(<Login />);
    
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
  });

  it('validates email format', async () => {
    render(<Login />);
    
    const emailInput = screen.getByLabelText(/email/i);
    const submitButton = screen.getByRole('button', { name: /login/i });
    
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/invalid email/i)).toBeInTheDocument();
    });
  });

  it('validates password length', async () => {
    render(<Login />);
    
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /login/i });
    
    fireEvent.change(passwordInput, { target: { value: '123' } });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(screen.getByText(/password too short/i)).toBeInTheDocument();
    });
  });

  it('submits form with valid data', async () => {
    const mockLogin = vi.fn();
    vi.mocked(require('../../store/auth').useAuthStore).mockReturnValue({
      login: mockLogin,
      isLoading: false,
      error: null
    });
    
    render(<Login />);
    
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /login/i });
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    fireEvent.click(submitButton);
    
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        email: 'test@example.com',
        password: 'password123'
      });
    });
  });

  it('shows loading state during submission', () => {
    vi.mocked(require('../../store/auth').useAuthStore).mockReturnValue({
      login: vi.fn(),
      isLoading: true,
      error: null
    });
    
    render(<Login />);
    
    expect(screen.getByRole('button', { name: /logging in/i })).toBeDisabled();
  });

  it('displays error message when login fails', () => {
    const errorMessage = 'Invalid credentials';
    vi.mocked(require('../../store/auth').useAuthStore).mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: errorMessage
    });
    
    render(<Login />);
    
    expect(screen.getByText(errorMessage)).toBeInTheDocument();
  });

  it('clears error when user starts typing', async () => {
    const errorMessage = 'Invalid credentials';
    vi.mocked(require('../../store/auth').useAuthStore).mockReturnValue({
      login: vi.fn(),
      isLoading: false,
      error: errorMessage
    });
    
    render(<Login />);
    
    expect(screen.getByText(errorMessage)).toBeInTheDocument();
    
    const emailInput = screen.getByLabelText(/email/i);
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    
    await waitFor(() => {
      expect(screen.queryByText(errorMessage)).not.toBeInTheDocument();
    });
  });

  it('handles form reset', () => {
    render(<Login />);
    
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const resetButton = screen.getByRole('button', { name: /reset/i });
    
    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    
    fireEvent.click(resetButton);
    
    expect(emailInput).toHaveValue('');
    expect(passwordInput).toHaveValue('');
  });
});
