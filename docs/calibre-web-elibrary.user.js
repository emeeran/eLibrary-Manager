// ==UserScript==
// @name         Calibre-Web → eLibrary Manager Reader
// @namespace    elibrary-manager
// @version      1.0.0
// @description  Rewrites Calibre-Web's "Read in web browser" links to open the book directly in the local eLibrary Manager reader (by title).
// @match        *://calibre-web-em.ashiknesin.com/*
// @match        *://localhost/*
// @match        *://127.0.0.1/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==
//
// INSTALL
//   1. Install Tampermonkey (Chrome/Edge/Firefox) or Greasemonkey (Firefox).
//   2. Tampermonkey → Dashboard → + (new script) → paste this file → save.
//   3. Edit @match above (and ELM_URL below) to match YOUR Calibre-Web URL and
//      the host/port where eLibrary Manager runs.
//
// HOW IT WORKS
//   Calibre-Web's "Read in web browser" link normally opens Calibre-Web's own
//   reader in a new tab. This script rewrites those links to point at eLM's
//   /calibre/launch endpoint, which resolves the book by title (+ author) and
//   302-redirects to eLM's reader. The link opens in the SAME tab (Calibre-Web
//   → eLM reader); use the browser's back button to return to Calibre-Web.

(function () {
    'use strict';

    // === CONFIG ===
    const ELM_URL = 'http://localhost:8001'; // eLibrary Manager base URL
    // ===============

    const READ_HREF = /\/read\/\d+/i; // Calibre-Web reader link pattern

    /** Best-effort title for the book a Read link belongs to. */
    function titleFor(link) {
        let scope = link.closest(
            '[class*="book"], [class*="media"], [class*="card"], li, article, section, .container, body'
        );
        while (scope && scope.tagName !== 'BODY') {
            const t = scope.querySelector(
                '[property="name"], .book-title, .title, h2, h3'
            );
            if (t && t.textContent.trim()) return t.textContent.trim();
            scope = scope.parentElement;
            if (!scope) break;
            scope = scope.closest(
                '[class*="book"], [class*="media"], [class*="card"], li, article, section, .container, body'
            ) || scope.parentElement;
        }
        // Page-level fallback (book detail page).
        return (
            document.querySelector('[property="name"], .book-title, h2')?.textContent?.trim() ||
            document.title
        );
    }

    /** Best-effort author for the book a Read link belongs to. */
    function authorFor(link) {
        const scope =
            link.closest('[class*="book"], [class*="media"], li, article, section, body') ||
            document;
        return (
            scope.querySelector('[property="author"], .author, .book-author')?.textContent?.trim() ||
            ''
        );
    }

    function rewrite(link) {
        if (!READ_HREF.test(link.getAttribute('href') || '')) return;
        if (link.dataset.elmRewritten === '1') return;
        const title = titleFor(link);
        if (!title) return;
        const author = authorFor(link);
        const params = new URLSearchParams({ title });
        if (author) params.set('author', author);
        link.setAttribute('href', `${ELM_URL}/calibre/launch?${params.toString()}`);
        link.removeAttribute('target'); // open in the SAME tab, not a new one
        link.dataset.elmRewritten = '1';
    }

    function rewriteAll() {
        document.querySelectorAll('a[href]').forEach(rewrite);
    }

    rewriteAll();

    // Re-run when Calibre-Web injects content dynamically.
    const obs = new MutationObserver(() => rewriteAll());
    obs.observe(document.body, { childList: true, subtree: true });
})();
