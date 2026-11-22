export interface User {
  id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  created_at: string;
}

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface MessageResponse {
  message: string;
}
