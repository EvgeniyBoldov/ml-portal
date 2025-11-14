import { apiRequest } from './http';
import type { LoginResponse, User } from './types';

export async function login(
  login: string,
  password: string
): Promise<LoginResponse> {
  return apiRequest<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login, password }),
  });
}

export async function me(): Promise<User> {
  return apiRequest<User>('/auth/me', { method: 'GET' });
}

export async function logout(): Promise<void> {
  return apiRequest<void>('/auth/logout', { method: 'POST' });
}
