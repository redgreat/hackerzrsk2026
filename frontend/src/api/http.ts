const TOKEN_KEY = 'coach_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => (onUnauthorized = fn)

export async function rawFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const resp = await fetch(`/api${path}`, { ...init, headers })
  if (!resp.ok) {
    let message = `请求失败（${resp.status}）`
    try {
      const data = await resp.json()
      message = data.message ?? (typeof data.detail === 'string' ? data.detail : message)
    } catch {
      /* 非 JSON 错误体 */
    }
    if (resp.status === 401) {
      tokenStore.clear()
      onUnauthorized()
    }
    throw new ApiError(resp.status, message)
  }
  return resp
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await rawFetch(path, init)).json() as Promise<T>
}

export const get = <T>(path: string) => request<T>(path)
export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
