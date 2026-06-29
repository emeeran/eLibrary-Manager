/**
 * Reader: client-side in-chapter text search.
 *
 * Walks text nodes in the chapter content, wraps matches in <mark> elements,
 * and provides prev/next navigation through the results.
 */

let _searchDebounce = null;
let _searchMatches = [];
let _currentMatchIndex = -1;

/**
 * Handle search input with debounce
 */
function handleSearch(event) {
    if (event && event.key === 'Escape') { clearSearch(); return; }
    const query = document.getElementById('ic-search-input').value.trim();
    const clearBtn = document.getElementById('ic-search-clear');

    if (clearBtn) {
        clearBtn.style.display = query ? 'flex' : 'none';
    }

    clearTimeout(_searchDebounce);

    if (!query) { clearSearch(); return; }

    if (query.length < 2) {
        clearHighlights();
        _searchMatches = [];
        _currentMatchIndex = -1;
        document.getElementById('ic-search-results').innerHTML = `
            <div class="ic-sidebar-empty">
                <div class="ic-sidebar-empty-icon">${EmptyStateIcons.search}</div>
                <div class="ic-sidebar-empty-text">Keep typing...</div>
                <div class="ic-sidebar-empty-hint">Enter at least 2 characters to search</div>
            </div>`;
        return;
    }

    _searchDebounce = setTimeout(() => _performClientSearch(query), 300);
}

/**
 * Client-side in-chapter text search.
 * Walks text nodes in ic-chapter-text, wraps matches in <mark> elements.
 */
function _performClientSearch(query) {
    clearHighlights();
    const container = document.getElementById('ic-chapter-text');
    if (!container) return;

    const resultsEl = document.getElementById('ic-search-results');

    // Walk text nodes and wrap matches
    const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
    const textNodes = [];
    let node;
    while (node = walker.nextNode()) {
        if (node.parentNode && node.parentNode.nodeName === 'MARK') continue;
        if (node.parentNode && (node.parentNode.nodeName === 'SCRIPT' || node.parentNode.nodeName === 'STYLE')) continue;
        textNodes.push(node);
    }

    const queryLower = query.toLowerCase();
    _searchMatches = [];

    textNodes.forEach(textNode => {
        const text = textNode.textContent;
        const lower = text.toLowerCase();
        let idx = lower.indexOf(queryLower);
        if (idx === -1) return;

        const parent = textNode.parentNode;
        if (!parent) return;

        const fragment = document.createDocumentFragment();
        let lastIdx = 0;

        while (idx !== -1) {
            if (idx > lastIdx) {
                fragment.appendChild(document.createTextNode(text.substring(lastIdx, idx)));
            }
            const span = document.createElement('mark');
            span.className = 'ic-search-match';
            span.textContent = text.substring(idx, idx + query.length);
            _searchMatches.push(span);
            fragment.appendChild(span);
            lastIdx = idx + query.length;
            idx = lower.indexOf(queryLower, lastIdx);
        }
        if (lastIdx < text.length) {
            fragment.appendChild(document.createTextNode(text.substring(lastIdx)));
        }
        parent.replaceChild(fragment, textNode);
    });

    // Update results display with navigation
    if (_searchMatches.length > 0) {
        _currentMatchIndex = 0;
        _searchMatches[0].classList.add('ic-search-current');
        _searchMatches[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
        _renderSearchNav();
    } else {
        _currentMatchIndex = -1;
        resultsEl.innerHTML = '<div class="ic-sidebar-empty">No matches found in this chapter.</div>';
    }
}

/**
 * Render search results navigation (match count + prev/next buttons)
 */
function _renderSearchNav() {
    const resultsEl = document.getElementById('ic-search-results');
    if (!resultsEl || _searchMatches.length === 0) return;

    resultsEl.innerHTML = `
        <div class="ic-search-nav">
            <button class="ic-search-nav-btn" onclick="searchPrevMatch()" title="Previous match">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/></svg>
            </button>
            <span class="ic-search-status">${_currentMatchIndex + 1} of ${_searchMatches.length} matches</span>
            <button class="ic-search-nav-btn" onclick="searchNextMatch()" title="Next match">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8.59 16.59L10 18l6-6-6-6-1.41 1.41L13.17 12z"/></svg>
            </button>
        </div>`;
}

/**
 * Navigate to next search match
 */
function searchNextMatch() {
    if (_searchMatches.length === 0) return;
    _searchMatches[_currentMatchIndex].classList.remove('ic-search-current');
    _currentMatchIndex = (_currentMatchIndex + 1) % _searchMatches.length;
    _searchMatches[_currentMatchIndex].classList.add('ic-search-current');
    _searchMatches[_currentMatchIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
    _renderSearchNav();
}

/**
 * Navigate to previous search match
 */
function searchPrevMatch() {
    if (_searchMatches.length === 0) return;
    _searchMatches[_currentMatchIndex].classList.remove('ic-search-current');
    _currentMatchIndex = (_currentMatchIndex - 1 + _searchMatches.length) % _searchMatches.length;
    _searchMatches[_currentMatchIndex].classList.add('ic-search-current');
    _searchMatches[_currentMatchIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
    _renderSearchNav();
}

/**
 * Remove all search highlight marks from chapter text.
 * Restores original text nodes by unwrapping <mark class="ic-search-match"> elements.
 */
function clearHighlights() {
    const container = document.getElementById('ic-chapter-text');
    if (!container) return;

    const marks = container.querySelectorAll('mark.ic-search-match');
    marks.forEach(mark => {
        const parent = mark.parentNode;
        if (parent) {
            parent.replaceChild(document.createTextNode(mark.textContent), mark);
            parent.normalize();
        }
    });
    _searchMatches = [];
    _currentMatchIndex = -1;
}

/**
 * Clear search input and highlights
 */
function clearSearch() {
    clearHighlights();
    const input = document.getElementById('ic-search-input');
    const clearBtn = document.getElementById('ic-search-clear');
    const results = document.getElementById('ic-search-results');

    if (input) input.value = '';
    if (clearBtn) clearBtn.style.display = 'none';
    if (results) results.innerHTML = `
        <div class="ic-sidebar-empty">
            <div class="ic-sidebar-empty-icon">${EmptyStateIcons.search}</div>
            <div class="ic-sidebar-empty-text">Search this chapter</div>
            <div class="ic-sidebar-empty-hint">Enter at least 2 characters to search</div>
        </div>`;
}
