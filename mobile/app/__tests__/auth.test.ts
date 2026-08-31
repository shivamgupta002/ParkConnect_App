import * as SecureStore from 'expo-secure-store';

// --- Mock axios so both api.ts's `api` instance and auth.ts's internal
// refreshClient point at the same controllable fake. Names must start with
// "mock" so babel-plugin-jest-hoist allows referencing them inside the
// hoisted jest.mock factory below.
const mockPost = jest.fn();
const mockRequest = jest.fn(); // used for `api(originalRequest)` retries
let mockResponseError: (error: any) => any;

jest.mock('axios', () => {
  const instance: any = jest.fn((config: any) => mockRequest(config));
  instance.post = (...args: any[]) => mockPost(...args);
  instance.get = jest.fn();
  instance.interceptors = {
    request: { use: (fn: any) => fn },
    response: {
      use: (success: any, error: any) => {
        mockResponseError = error;
      },
    },
  };
  const create = jest.fn(() => instance);
  return { __esModule: true, default: { create }, create };
});

import { registerUser, verifyOtp, extractErrorMessage } from '@/lib/auth-api';
import { saveTokens, getAccessToken, clearTokens } from '@/lib/auth';
import '@/lib/api'; // side-effect import: registers the interceptors above

function makeAxiosError(status: number, detail: string) {
  return { isAxiosError: true, response: { status, data: { detail } } };
}

beforeEach(async () => {
  mockPost.mockReset();
  mockRequest.mockReset();
  await clearTokens();
});

describe('register -> verify-otp happy path', () => {
  it('stores tokens after a successful register + verify-otp flow', async () => {
    mockPost.mockResolvedValueOnce({ data: { message: 'Registration successful.' } });
    mockPost.mockResolvedValueOnce({
      data: { access_token: 'access-123', refresh_token: 'refresh-456', token_type: 'bearer' },
    });

    await registerUser({
      full_name: 'Asha Rao',
      email: 'asha@example.com',
      phone_number: '+919876543210',
      password: 'Password123',
    });
    expect(mockPost).toHaveBeenNthCalledWith(
      1,
      '/auth/register',
      expect.objectContaining({ email: 'asha@example.com' })
    );

    const tokens = await verifyOtp({ phone_number: '+919876543210', code: '123456' });
    await saveTokens(tokens.access_token, tokens.refresh_token);

    expect(await getAccessToken()).toBe('access-123');
    expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
      expect.stringContaining('access_token'),
      'access-123'
    );
  });
});

describe('wrong OTP code', () => {
  it('surfaces the backend error message', async () => {
    mockPost.mockRejectedValueOnce(makeAxiosError(400, 'Invalid or expired code'));

    let caught: unknown;
    try {
      await verifyOtp({ phone_number: '+919876543210', code: '000000' });
    } catch (error) {
      caught = error;
    }

    expect(caught).toBeDefined();
    expect(extractErrorMessage(caught)).toBe('Invalid or expired code');
  });
});

describe('401 on a protected call', () => {
  it('attempts exactly one refresh and retries the original request', async () => {
    await saveTokens('expired-access-token', 'valid-refresh-token');

    mockPost.mockResolvedValueOnce({
      data: { access_token: 'new-access-token', token_type: 'bearer' },
    }); // POST /auth/refresh
    mockRequest.mockResolvedValueOnce({ data: { ok: true } }); // retried request

    const originalRequest: any = { url: '/vehicles', headers: {} };
    const error = { response: { status: 401 }, config: originalRequest };

    const result = await mockResponseError(error);

    expect(result).toEqual({ data: { ok: true } });
    const refreshCalls = mockPost.mock.calls.filter(([url]: [string]) => url === '/auth/refresh');
    expect(refreshCalls).toHaveLength(1);
    expect(mockRequest).toHaveBeenCalledTimes(1);
    expect(originalRequest.headers.Authorization).toBe('Bearer new-access-token');
  });

  it('does not refresh again on an already-retried request', async () => {
    await saveTokens('expired-access-token', 'valid-refresh-token');

    const originalRequest: any = { url: '/vehicles', headers: {}, _retry: true };
    const error = { response: { status: 401 }, config: originalRequest };

    await expect(mockResponseError(error)).rejects.toBe(error);
    expect(mockPost).not.toHaveBeenCalled();
  });
});