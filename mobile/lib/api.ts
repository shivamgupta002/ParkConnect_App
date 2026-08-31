import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getAccessToken, refreshAccessToken, clearTokens } from './auth';

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

const AUTH_PATH_PREFIX = '/auth/';

function isAuthEndpoint(url?: string): boolean {
  return !!url && url.includes(AUTH_PATH_PREFIX);
}

// Attach the stored access token to every request except /auth/* itself.
api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  if (!isAuthEndpoint(config.url)) {
    const token = await getAccessToken();
    if (token) {
      config.headers = config.headers ?? {};
      (config.headers as any).Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Coalesces concurrent 401s into a single refresh call instead of firing
// /auth/refresh once per in-flight request.
let refreshPromise: Promise<string> | null = null;

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as
      | (InternalAxiosRequestConfig & { _retry?: boolean })
      | undefined;

    const shouldAttemptRefresh =
      error.response?.status === 401 &&
      originalRequest &&
      !originalRequest._retry &&
      !isAuthEndpoint(originalRequest.url);

    if (!shouldAttemptRefresh) {
      return Promise.reject(error);
    }

    originalRequest!._retry = true;

    try {
      if (!refreshPromise) {
        refreshPromise = refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
      }
      const newAccessToken = await refreshPromise;

      originalRequest!.headers = originalRequest!.headers ?? {};
      (originalRequest!.headers as any).Authorization = `Bearer ${newAccessToken}`;

      // Not navigating here on purpose — a failed refresh just rejects, and
      // the app's root layout (Phase R2) is responsible for redirecting to
      // login when it sees no valid tokens.
      return api(originalRequest!);
    } catch (refreshError) {
      await clearTokens();
      return Promise.reject(refreshError);
    }
  }
);

export default api;