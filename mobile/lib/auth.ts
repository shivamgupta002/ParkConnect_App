import * as SecureStore from 'expo-secure-store';
import axios from 'axios';

const ACCESS_TOKEN_KEY = 'parkconnect_access_token';
const REFRESH_TOKEN_KEY = 'parkconnect_refresh_token';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

// A separate plain axios instance (not the interceptor-wired `api` from
// ./api) so refreshing a token can never itself trigger the 401 -> refresh
// -> retry loop.
const refreshClient = axios.create({ baseURL: API_BASE_URL, timeout: 15000 });

export async function saveTokens(accessToken: string, refreshToken: string): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken),
    SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken),
  ]);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}

/**
 * Exchanges the stored refresh_token for a new access_token via
 * POST /auth/refresh, persists it, and returns it. Throws if there's no
 * stored refresh token or the backend rejects it (expired/invalid) — the
 * caller treats that as "logged out".
 */
export async function refreshAccessToken(): Promise<string> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await refreshClient.post<{ access_token: string; token_type: string }>(
    '/auth/refresh',
    { refresh_token: refreshToken }
  );

  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, response.data.access_token);
  return response.data.access_token;
}