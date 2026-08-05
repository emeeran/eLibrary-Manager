/**
 * lib/dom.js — shared DOM / HTML helpers.
 *
 * Classic script (loaded before the reader/library modules) so its declarations
 * land on the global scope and are visible to subsequently-loaded scripts and
 * inline handlers. Pure utilities with no app state.
 *
 * Adoption is incremental: existing monoliths still define some of these
 * locally; as modules migrate they drop their private copies and rely on these.
 */

/* exported escapeHtml, escapeAttr, qs, qsa, el, debounce, throttle, setTrustedHTML */

// --- HTML escaping ---------------------------------------------------------

const _DOM_ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const _DOM_ESC_RE = /[&<>"']/g;

/**
 * Escape a value for safe interpolation into HTML text or an attribute.
 * Null/undefined → ''. Escapes &, <, >, ", '.
 */
function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(_DOM_ESC_RE, (c) => _DOM_ESC_MAP[c]);
}

/** Alias making the attribute-context intent explicit. */
function escapeAttr(text) {
    return escapeHtml(text);
}

// --- Query helpers ---------------------------------------------------------

function qs(selector, root = document) {
    return root.querySelector(selector);
}

function qsa(selector, root = document) {
    return Array.from(root.querySelectorAll(selector));
}

/** Create an element from a tag + attrs map ({class, text, html, …}). */
function el(tag, attrs = {}) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
        if (key === 'class') node.className = value;
        else if (key === 'text') node.textContent = value;
        else if (key === 'html') setTrustedHTML(node, value);
        else node.setAttribute(key, value);
    }
    return node;
}

// --- Rate-limiting helpers -------------------------------------------------

/** Debounce: call ``fn`` after ``wait`` ms of quiet, trailing edge. */
function debounce(fn, wait = 200) {
    let timer = null;
    return function debounced(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), wait);
    };
}

/** Throttle: call ``fn`` at most once per ``limit`` ms (leading edge). */
function throttle(fn, limit = 100) {
    let last = 0;
    let timer = null;
    return function throttled(...args) {
        const now = Date.now();
        const remaining = limit - (now - last);
        if (remaining <= 0) {
            clearTimeout(timer);
            timer = null;
            last = now;
            fn.apply(this, args);
        } else if (!timer) {
            timer = setTimeout(() => {
                last = Date.now();
                timer = null;
                fn.apply(this, args);
            }, remaining);
        }
    };
}

// --- Trusted HTML ----------------------------------------------------------

/**
 * Set pre-sanitized HTML. Book HTML is sanitized server-side with nh3; this
 * wrapper keeps the trust boundary visible at every call site. NEVER pass an
 * unsanitized string here.
 */
function setTrustedHTML(element, html) {
    if (element) element.innerHTML = html;
}
