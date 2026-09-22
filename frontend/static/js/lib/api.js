/**
 * lib/api.js — canonical fetch wrapper for the eLibrary Manager frontend.
 *
 * Classic script (global scope). Two layers:
 *
 *   1. ``apiFetch(url, options, retries)`` — a raw ``fetch`` wrapper with
 *      bounded retry for transient failures (NAS stalls, 5xx, 408/425/429).
 *      Returns the ``Response`` (does NOT throw on HTTP status), mirroring the
 *      behaviour the reader's ``fetchRetry`` relied on. Migrate call sites to
 *      this as modules are modernized.
 *
 *   2. ``apiGet`` / ``apiPost`` / ``apiPut`` / ``apiDelete`` — JSON conveniences
 *      that retry, throw ``ApiError`` on a non-2xx status, and return parsed
 *      JSON. ``apiBeacon`` fires a best-effort ``navigator.sendBeacon``.
 *
 * Same-origin CSRF needs no token header: ``CSRFMiddleware`` checks the Origin
 * header, which the browser always sends.
 */

/* exported ApiError, apiFetch, apiRequest, apiGet, apiPost, apiPut, apiDelete, apiBeacon */

class ApiError extends Error {
  constructor(message, { status = 0, response = null, body = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.response = response;
    this.body = body;
  }
}

const _API_BACKOFF = [400, 800, 1500];

/**
 * ``fetch`` with bounded retry for transient failures.
 *
 * Retries network errors and responses that are 5xx, 408, 425, or 429. A
 * definitive 4xx (e.g. 404) is returned immediately — it won't fix itself.
 */
async function apiFetch(url, options = {}, retries = 3) {
  let lastErr = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, options);
      if (
        response.ok ||
        (response.status >= 400 &&
          response.status < 500 &&
          response.status !== 408 &&
          response.status !== 425 &&
          response.status !== 429)
      ) {
        return response;
      }
      lastErr = new Error(`HTTP ${response.status}`);
    } catch (e) {
      lastErr = e; // network error — retry
    }
    if (attempt < retries) {
      await new Promise((r) => setTimeout(r, _API_BACKOFF[attempt] ?? 1500));
    }
  }
  throw lastErr || new Error("Request failed");
}

/** JSON convenience: retry, throw ApiError on non-2xx, return parsed body. */
async function apiRequest(url, options = {}) {
  const response = await apiFetch(url, options);
  if (!response.ok) {
    let body = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    const detail =
      (body && (body.detail || body.error || body.message)) ||
      `HTTP ${response.status}`;
    throw new ApiError(detail, { status: response.status, response, body });
  }
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response.text();
}

function _jsonOptions(method, body, options) {
  return {
    method,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    body: body == null ? undefined : JSON.stringify(body),
    ...options,
  };
}

function apiGet(url, options = {}) {
  return apiRequest(url, { method: "GET", ...options });
}

function apiPost(url, body, options = {}) {
  return apiRequest(url, _jsonOptions("POST", body, options));
}

function apiPut(url, body, options = {}) {
  return apiRequest(url, _jsonOptions("PUT", body, options));
}

function apiDelete(url, options = {}) {
  return apiRequest(url, { method: "DELETE", ...options });
}

/** Best-effort fire-and-forget (page unload, analytics). Returns success bool. */
function apiBeacon(url, body) {
  try {
    if (navigator.sendBeacon) {
      return navigator.sendBeacon(
        url,
        body == null ? undefined : JSON.stringify(body),
      );
    }
  } catch {
    // ignore — best effort
  }
  return false;
}
