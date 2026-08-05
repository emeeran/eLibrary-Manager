/**
 * lib/storage.js — safe localStorage helpers.
 *
 * Classic script (global scope). ``get`` tries JSON first and falls back to the
 * raw string, so it works for both JSON values (``storage.set``) and legacy raw
 * strings (e.g. ``localStorage.setItem('reader-theme', 'day')``). All accessors
 * are wrapped so private-browsing mode or a full quota can't throw into app
 * code.
 */

/* exported storageGet, storageSet, storageGetRaw, storageSetRaw, storageRemove */

const _STORAGE_MEM = new Map(); // fallback when localStorage is unavailable

function _ls() {
    try {
        return globalThis.localStorage ?? null;
    } catch {
        return null; // localStorage access can throw in some sandboxed contexts
    }
}

/**
 * Read ``key``. Tries JSON.parse; on failure (or a raw string) returns the raw
 * value; returns ``defaultValue`` if absent. Never throws.
 */
function storageGet(key, defaultValue = null) {
    const ls = _ls();
    let raw;
    if (ls) {
        try {
            raw = ls.getItem(key);
        } catch {
            raw = _STORAGE_MEM.has(key) ? _STORAGE_MEM.get(key) : null;
        }
    } else {
        raw = _STORAGE_MEM.has(key) ? _STORAGE_MEM.get(key) : null;
    }
    if (raw == null) return defaultValue;
    try {
        return JSON.parse(raw);
    } catch {
        return raw; // legacy raw string — return as-is
    }
}

/** Write ``value`` as JSON. Returns true on success, false on quota/error. */
function storageSet(key, value) {
    let raw;
    try {
        raw = JSON.stringify(value);
    } catch {
        return false;
    }
    const ls = _ls();
    if (ls) {
        try {
            ls.setItem(key, raw);
            return true;
        } catch {
            _STORAGE_MEM.set(key, raw); // quota exceeded / disabled — keep in memory
            return false;
        }
    }
    _STORAGE_MEM.set(key, raw);
    return false;
}

/** Read ``key`` as a raw string (no JSON parsing). */
function storageGetRaw(key, defaultValue = null) {
    const ls = _ls();
    if (ls) {
        try {
            const raw = ls.getItem(key);
            return raw == null ? defaultValue : raw;
        } catch {
            return _STORAGE_MEM.has(key) ? _STORAGE_MEM.get(key) : defaultValue;
        }
    }
    return _STORAGE_MEM.has(key) ? _STORAGE_MEM.get(key) : defaultValue;
}

/** Write ``value`` as a raw string (no JSON encoding). Returns success bool. */
function storageSetRaw(key, value) {
    const raw = String(value);
    const ls = _ls();
    if (ls) {
        try {
            ls.setItem(key, raw);
            return true;
        } catch {
            _STORAGE_MEM.set(key, raw);
            return false;
        }
    }
    _STORAGE_MEM.set(key, raw);
    return false;
}

/** Remove ``key``. */
function storageRemove(key) {
    const ls = _ls();
    if (ls) {
        try {
            ls.removeItem(key);
        } catch {
            // ignore
        }
    }
    _STORAGE_MEM.delete(key);
}
