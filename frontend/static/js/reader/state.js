/**
 * Reader: shared state and UI utilities.
 *
 * Loaded first. Declares the global `IcecreamReader` state object plus the
 * small DOM/HTML helpers used across every other reader module. Top-level
 * `const`/`let` in a classic script are visible to all subsequently-loaded
 * classic scripts (shared global lexical environment), and `function`
 * declarations additionally become properties of `window`.
 */

// Global state
const IcecreamReader = {
    bookId: null,
    currentChapter: 0,
    totalChapters: 0,
    chapters: [],
    zoomLevel: 100,
    theme: 'day',
    tocVisible: true,
    summaryVisible: false,
    loading: false,
    // Layout & Display
    pageLayout: 'single',
    fontSize: 15,
    lineHeight: 1.5,
    // Volume
    volume: 80,
    // Right panel state
    activeRightPanel: null, // 'bookinfo', 'settings', 'summary', or null
    // TTS State (synced from tts.js callbacks; audio managed by tts.js)
    ttsEnabled: false,
    ttsPlaying: false,
    ttsVoices: [],
    ttsCurrentVoice: null,
    ttsRate: 1.0,
    // Caching & Performance
    chapterCache: new Map(),
    isPrefetching: false,
    maxCacheSize: 10,
    // Page tracking
    chapterPageCounts: {},  // { chapterIndex: estimatedPages }
    // Progress saving
    progressSaveTimeout: null,
    progressSaveDelay: 2000,
    // Summary options
    summaryLength: localStorage.getItem('reader-summary-length') || 'medium',
    autoSummary: localStorage.getItem('reader-auto-summary') === 'true',
    // Current active left panel
    activeLeftPanel: 'toc'
};

// Empty state SVG icons
const EmptyStateIcons = {
    bookmark: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2z"/></svg>',
    note: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>',
    search: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>'
};

/**
 * Convert a stored book cover path into a valid `/covers/...` URL.
 *
 * The DB stores cover paths inconsistently: the scanner writes absolute
 * filesystem paths (e.g. `/home/.../static_covers/<hash>.jpg`) while the
 * upload endpoint writes a bare filename. The browser needs the served URL.
 * This normalizes any of {absolute path, relative path, bare filename,
 * already-a-URL} to `/covers/<basename>`.
 */
function coverUrl(coverPath) {
    if (!coverPath) return '';
    if (coverPath.startsWith('/covers/') || coverPath.startsWith('http')) return coverPath;
    const base = coverPath.split('/').pop();
    return '/covers/' + encodeURIComponent(base);
}

/**
 * fetch() wrapper with bounded retry for transient failures.
 *
 * NAS-backed books occasionally return a transient 400/5xx (or a network error)
 * when the mount stalls for a moment; a single failed read shouldn't kill the
 * reader. We retry a few times with backoff before giving up and surfacing the
 * error. 4xx responses other than 408/429 are not retried (they won't fix
 * themselves on a chapter load).
 */
async function fetchRetry(url, options = {}, retries = 3) {
    const backoff = [400, 800, 1500];
    let lastErr = null;
    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const response = await fetch(url, options);
            // Retry only transient / server classes.
            if (
                response.ok ||
                (response.status >= 400 && response.status < 500 &&
                 response.status !== 408 && response.status !== 425 && response.status !== 429)
            ) {
                return response;
            }
            lastErr = new Error(`HTTP ${response.status}`);
        } catch (e) {
            lastErr = e; // network error — retry
        }
        if (attempt < retries) {
            await new Promise(r => setTimeout(r, backoff[attempt] ?? 1500));
        }
    }
    throw lastErr || new Error('Request failed');
}

/**
 * Escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Escape regex special characters
 */
function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Show error message
 */
function showError(message) {
    const contentArea = document.getElementById('ic-chapter-text');
    contentArea.innerHTML = `
        <div role="alert" aria-live="assertive" style="text-align: center; padding: 40px; color: #d32f2f;">
            <p>${escapeHtml(message)}</p>
        </div>
    `;
}

/**
 * Show toast message
 */
function showToast(message, options = {}) {
    let container = document.getElementById('ic-toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'ic-toast-container';
        container.className = 'ic-toast-container';
        document.body.appendChild(container);
    }

    // Cap at 3 visible toasts
    while (container.children.length >= 3) {
        container.firstChild.remove();
    }

    const toast = document.createElement('div');
    toast.className = 'ic-toast';
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('ic-toast-out');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}
