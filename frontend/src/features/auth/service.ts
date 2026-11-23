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

  async getAuthMethods(): Promise<{ google_enabled: boolean; email_otp_enabled: boolean }> {
    return ApiClient.get<{ google_enabled: boolean; email_otp_enabled: boolean }>('/api/v1/auth/methods');
  },

  async requestEmailOtp(email: string): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/otp/request', { email });
  },

  async verifyEmailOtp(email: string, code: string): Promise<TokenResponse> {
    return ApiClient.post<TokenResponse>('/api/v1/auth/otp/verify', { email, code });
  },

  async requestPasswordResetOtp(email: string): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/password-otp/request', { email });
  },

  async resetPasswordWithOtp(email: string, code: string, newPassword: string): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/password-otp/reset', {
      email,
      code,
      new_password: newPassword,
    });
  },
};
