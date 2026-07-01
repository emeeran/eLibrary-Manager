// ==UserScript==
// @name         Calibre-Web → eLibrary Manager Reader
// @namespace    elibrary-manager
// @version      1.1.0
// @description  Open Calibre-Web's "Read in web browser" books in the local eLibrary Manager reader (by title). Rewrites links + intercepts clicks; same tab.
// @match        *://calibre-web-em.ashiknesin.com/*
// @match        *://*.ashiknesin.com/*
// @match        *://localhost/*
// @match        *://127.0.0.1/*
// @run-at       document-start
// @grant        none
// ==/UserScript==
//
// If the Tampermonkey icon shows NO badge on a Calibre-Web page, the @match
// isn't hitting your URL — edit the @match lines to your exact Calibre-Web host.

(function () {
    'use strict';

    // === CONFIG ===
    const ELM_URL = 'http://localhost:8001'; // eLibrary Manager base URL
    const DEBUG = true; // logs to the browser DevTools console
    // ===============

    const L = (...a) => DEBUG && console.log('[eLM]', ...a);

    // Calibre-Web reader link patterns (href or route). Broadened to catch
    // /read/<id>, /read/<id>/<fmt>, /readbook/<id>, and query-form variants.
    const READ_RE = /\/(read|readbook)\b/i;
    // Link/button text that indicates a "read in browser" affordance.
    const READ_TEXT_RE = /read.*(in.*browser|online|book)|readbook/i;

    function isReadAffordance(el) {
        if (!el || el.tagName !== 'A' && el.tagName !== 'BUTTON' && !el.getAttribute?.('onclick')) {
            // still allow anchors detected by href below
        }
        const a = el.closest?.('a, button, [role="button"]');
        if (!a) return false;
        const href = a.getAttribute('href') || '';
        const text = (a.textContent || '').trim();
        return READ_RE.test(href) || READ_TEXT_RE.test(text) || READ_RE.test(text);
    }

    function titleFor(el) {
        let scope = el.closest?.('[class*="book"], [class*="media"], [class*="card"], li, article, section, .container, body') || document;
        let node = scope;
        while (node && node.tagName !== 'BODY') {
            const t = node.querySelector('[property="name"], .book-title, .title, h2, h3');
            if (t && t.textContent.trim()) return t.textContent.trim();
            node = node.parentElement;
        }
        return (
            document.querySelector('[property="name"], .book-title, h2')?.textContent?.trim() ||
            document.title || ''
        );
    }

    function authorFor(el) {
        const scope = el.closest?.('[class*="book"], [class*="media"], li, article, section, body') || document;
        return scope.querySelector('[property="author"], .author, .book-author')?.textContent?.trim() || '';
    }

    function elmUrlFor(el) {
        const title = titleFor(el);
        if (!title) return null;
        const params = new URLSearchParams({ title });
        const author = authorFor(el);
        if (author) params.set('author', author);
        return `${ELM_URL}/calibre/launch?${params.toString()}`;
    }

    // 1) Rewrite anchor hrefs (so even middle-click/keyboard works) + drop target=_blank.
    function rewriteLinks() {
        document.querySelectorAll('a[href]').forEach((a) => {
            if (a.dataset.elm === '1') return;
            if (READ_RE.test(a.getAttribute('href') || '') ||
                READ_TEXT_RE.test((a.textContent || '').trim())) {
                const url = elmUrlFor(a);
                if (!url) return;
                a.setAttribute('href', url);
                a.removeAttribute('target');
                a.dataset.elm = '1';
                L('rewrote link ->', url);
            }
        });
    }

    // 2) Intercept clicks (capture) — catches buttons / JS handlers / late-rendered links.
    document.addEventListener('click', function (e) {
        const a = e.target.closest?.('a, button, [role="button"]');
        if (!a || a.dataset.elmIntercept === '1') {
            // fall through if not a read affordance
        }
        if (a && (READ_RE.test(a.getAttribute('href') || '') || READ_TEXT_RE.test((a.textContent || '').trim()))) {
            const url = elmUrlFor(a);
            if (url) {
                e.preventDefault();
                e.stopPropagation();
                L('intercepted click ->', url, '| title=', titleFor(a));
                window.location.href = url; // SAME tab
            } else {
                L('read affordance clicked but no title found for', a);
            }
        }
    }, true);

    // Run early + on DOM ready + on dynamic changes.
    rewriteLinks();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', rewriteLinks);
    }
    const obs = new MutationObserver(rewriteLinks);
    const startObs = () => obs.observe(document.body, { childList: true, subtree: true });
    if (document.body) startObs();
    else document.addEventListener('DOMContentLoaded', startObs);

    L('userscript active on', location.href);
})();
