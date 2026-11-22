import { ApiClient } from '@/lib/apiClient';
import type {
  LoginPayload,
  MessageResponse,
  RegisterPayload,
  TokenResponse,
  User,
} from './types';

export const authService = {
  async register(data: RegisterPayload): Promise<User> {
    return ApiClient.post<User>('/api/v1/auth/register', data);
  },

  async login(data: LoginPayload): Promise<TokenResponse> {
    return ApiClient.post<TokenResponse>('/api/v1/auth/login', data);
  },

  async refresh(): Promise<TokenResponse> {
    return ApiClient.post<TokenResponse>('/api/v1/auth/refresh');
  },

  async logout(): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/logout');
  },

  async getMe(): Promise<User> {
    return ApiClient.get<User>('/api/v1/auth/me');
  },

  async updateProfile(fullName: string): Promise<User> {
    return ApiClient.patch<User>('/api/v1/users/me', { full_name: fullName });
  },
};
