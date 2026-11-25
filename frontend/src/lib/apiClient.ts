type JsonBody = object;

class ApiClientError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

async function errorMessage(response: Response): Promise<string> {
  const contentType = response.headers.get('content-type') ?? '';

  if (contentType.includes('application/json')) {
    try {
      const body: unknown = await response.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        const detail = body.detail;
        if (typeof detail === 'string' && detail.trim()) return detail;
        if (Array.isArray(detail)) {
          const messages = detail
            .map((item) => {
              if (item && typeof item === 'object' && 'msg' in item) return String(item.msg);
              return typeof item === 'string' ? item : '';
            })
            .filter(Boolean);
          if (messages.length) return messages.join(' ');
        }
      }
    } catch {
      // Fall through to a generic status-based message for invalid JSON.
    }
  }

  return `Request failed (${response.status}).`;
}

function shouldRefresh(path: string, response: Response, retry: boolean): boolean {
  return (
    retry &&
    response.status === 401 &&
    !path.startsWith('/api/v1/auth/login') &&
    !path.startsWith('/api/v1/auth/register') &&
    !path.startsWith('/api/v1/auth/refresh') &&
    !path.startsWith('/api/v1/auth/otp/') &&
    !path.startsWith('/api/v1/auth/password-otp/')
  );
}

async function performRequest<T>(
  path: string,
  init: RequestInit,
  retryAfterRefresh: boolean,
): Promise<T> {
  const response = await fetch(path, { ...init, credentials: 'include' });

  if (shouldRefresh(path, response, retryAfterRefresh)) {
    const refreshResponse = await fetch('/api/v1/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    });
    if (refreshResponse.ok) return performRequest<T>(path, init, false);
  }

  if (!response.ok) throw new ApiClientError(await errorMessage(response), response.status);
  if (response.status === 204) return undefined as T;

  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) return (await response.text()) as T;
  return (await response.json()) as T;
}

function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');

  const hasBody = init.body !== undefined && init.body !== null;
  const isFormData = typeof FormData !== 'undefined' && init.body instanceof FormData;
  if (hasBody && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  return performRequest<T>(path, { ...init, headers }, true);
}

export const ApiClient = {
  get<T>(path: string, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'GET', signal });
  },

  post<T>(path: string, body?: JsonBody, signal?: AbortSignal): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  },

  patch<T>(path: string, body: JsonBody, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'PATCH', body: JSON.stringify(body), signal });
  },

  delete<T = void>(path: string, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'DELETE', signal });
  },
};
