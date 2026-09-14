/** The only module that sends backend requests. No mock queue or browser database. */
export const API_BASE_URL = globalThis.TABLETURN_CONFIG?.apiBaseUrl ||
  `http://${globalThis.location?.hostname || '127.0.0.1'}:8001`;

export class ApiError extends Error {
  constructor(message, status = 0, code = 'network_error') {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function createApiClient({baseUrl = API_BASE_URL, fetchImpl = globalThis.fetch,
  timeoutMs = 10000, onUnauthorized = () => {}} = {}) {
  const origin = baseUrl.replace(/\/$/, '');
  let session = null, bootstrap = null;
  const pending = new Map();

  async function send(path, method, body, key, csrf) {
    if (!path.startsWith('/api/')) throw new Error('Backend paths must begin with /api/.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetchImpl(origin + path, {
        method, credentials: 'include', cache: 'no-store', signal: controller.signal,
        headers: {Accept: 'application/json', ...(body ? {'Content-Type': 'application/json'} : {}),
          ...(csrf ? {'X-CSRF-Token': csrf} : {}), ...(key ? {'Idempotency-Key': key} : {})},
        body: body ? JSON.stringify(body) : undefined,
      });
      let result;
      try { result = await response.json(); }
      catch { throw new ApiError('The API returned an unreadable response. Please retry.', response.status, 'invalid_response'); }
      if (!response.ok) {
        if (response.status === 401 && path.startsWith('/api/staff/')) onUnauthorized();
        throw new ApiError(result.error?.message || 'The request could not be completed.', response.status, result.error?.code);
      }
      return result;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(controller.signal.aborted ? 'The request timed out. Please retry.' : 'Cannot reach the backend. Check that it is running and try again.');
    } finally { clearTimeout(timer); }
  }

  async function getSession(force = false) {
    if (session && !force) return session;
    if (!bootstrap) {
      bootstrap = send('/api/auth/session', 'GET').then(value => session = value).finally(() => bootstrap = null);
    }
    return bootstrap;
  }

  async function request(path, method = 'GET', body, key) {
    const write = method !== 'GET';
    if (write) await getSession();
    let result;
    try { result = await send(path, method, body, key, write ? session.csrf_token : null); }
    catch (error) {
      // Another tab may have rotated the shared cookie. Refresh once; preserve the mutation key.
      if (write && error.status === 403 && error.code === 'csrf_rejected') {
        await getSession(true);
        result = await send(path, method, body, key, session.csrf_token);
      } else throw error;
    }
    if (path === '/api/auth/login') session = result;
    if (path === '/api/auth/logout') session = null;
    return result;
  }

  async function mutate(path, body, method = 'POST') {
    const signature = method + path + JSON.stringify(body);
    const key = pending.get(signature) || crypto.randomUUID();
    pending.set(signature, key);
    try {
      const result = await request(path, method, body, key);
      pending.delete(signature);
      return result;
    } catch (error) {
      if (error.status >= 400 && error.status < 500) pending.delete(signature);
      throw error;
    }
  }

  return {request, mutate, getSession,
    login: (username, password) => request('/api/auth/login', 'POST', {username, password}),
    logout: () => request('/api/auth/logout', 'POST')};
}

export const backend = createApiClient({onUnauthorized: () => {
  if (globalThis.location) globalThis.location.href = '/staff/login';
}});
