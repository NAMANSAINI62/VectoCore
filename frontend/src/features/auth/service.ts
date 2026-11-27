import { ApiClient } from '@/lib/apiClient';
import type {
  AuthMethods,
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

  async logout(): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/logout');
  },

  async logoutAll(): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/logout-all', {});
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<MessageResponse> {
    return ApiClient.post<MessageResponse>('/api/v1/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },

  async getMe(): Promise<User> {
    return ApiClient.get<User>('/api/v1/auth/me');
  },

  async updateProfile(fullName: string): Promise<User> {
    return ApiClient.patch<User>('/api/v1/users/me', { full_name: fullName });
  },

  async getAuthMethods(): Promise<AuthMethods> {
    return ApiClient.get<AuthMethods>('/api/v1/auth/methods');
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
