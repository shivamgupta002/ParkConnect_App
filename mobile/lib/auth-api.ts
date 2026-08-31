import api from './api';

export interface MessageResponse {
  message: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function registerUser(payload: {
  full_name: string;
  email: string;
  phone_number: string;
  password: string;
}): Promise<MessageResponse> {
  const { data } = await api.post<MessageResponse>('/auth/register', payload);
  return data;
}

export async function verifyOtp(payload: {
  phone_number: string;
  code: string;
}): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/verify-otp', payload);
  return data;
}

export async function loginUser(payload: {
  email: string;
  password: string;
}): Promise<TokenResponse> {
  const { data } = await api.post<TokenResponse>('/auth/login', payload);
  return data;
}

export async function forgotPassword(payload: { email: string }): Promise<MessageResponse> {
  const { data } = await api.post<MessageResponse>('/auth/forgot-password', payload);
  return data;
}

export async function resetPassword(payload: {
  email: string;
  code: string;
  new_password: string;
}): Promise<MessageResponse> {
  const { data } = await api.post<MessageResponse>('/auth/reset-password', payload);
  return data;
}

// Extracts FastAPI's {"detail": "..."} error message; falls back to a
// generic message for network errors or unexpected shapes.
export function extractErrorMessage(
  error: unknown,
  fallback = 'Something went wrong. Please try again.'
): string {
  const detail = (error as any)?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}