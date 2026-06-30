/**
 * Reader: left/right sidebar panel management and book info panel data.
 */

/**
 * Close all left side panels
 */
function closeAllLeftPanels() {
    const panels = ['ic-toc-sidebar', 'ic-notes-sidebar', 'ic-bookmarks-sidebar', 'ic-search-sidebar'];
    panels.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (panel) panel.classList.add('collapsed');
    });

    // Deactivate all left tabs
    const tabs = ['ic-tab-contents', 'ic-tab-notes', 'ic-tab-bookmarks'];
    tabs.forEach(tabId => {
        const tab = document.getElementById(tabId);
        if (tab) tab.classList.remove('ic-tab-active');
    });
}

/**
 * Show a specific left panel
 */
function showLeftPanel(panelName, tabId) {
    closeAllLeftPanels();

    const panel = document.getElementById(panelName);
    if (panel) {
        panel.classList.remove('collapsed');
    }

    const tab = document.getElementById(tabId);
    if (tab) {
        tab.classList.add('ic-tab-active');
    }

    IcecreamReader.activeLeftPanel = panelName;
}

/**
 * Toggle TOC Panel
 */
function toggleTOCPanel() {
    const sidebar = document.getElementById('ic-toc-sidebar');

    if (IcecreamReader.activeLeftPanel === 'toc' && !sidebar.classList.contains('collapsed')) {
        sidebar.classList.add('collapsed');
        document.getElementById('ic-tab-contents')?.classList.remove('ic-tab-active');
    } else {
        showLeftPanel('ic-toc-sidebar', 'ic-tab-contents');
    }
}

/**
 * Show Notes Panel
 */
function showNotesPanel() {
    showLeftPanel('ic-notes-sidebar', 'ic-tab-notes');
    // The background chapter load skips the book-wide notes fetch when the
    // panel is closed, so refresh now that it's visible.
    renderNotes();
}

/**
 * Close Notes Panel
 */
function closeNotesPanel() {
    document.getElementById('ic-notes-sidebar').classList.add('collapsed');
    document.getElementById('ic-tab-notes')?.classList.remove('ic-tab-active');
}

/**
 * Show Bookmarks Panel
 */
function showBookmarksPanel() {
    showLeftPanel('ic-bookmarks-sidebar', 'ic-tab-bookmarks');
}

/**
 * Close Bookmarks Panel
 */
function closeBookmarksPanel() {
    document.getElementById('ic-bookmarks-sidebar').classList.add('collapsed');
    document.getElementById('ic-tab-bookmarks')?.classList.remove('ic-tab-active');
}

/**
 * Show Search Panel
 */
function showSearchPanel() {
    showLeftPanel('ic-search-sidebar', 'ic-tab-search');
    setTimeout(() => {
        document.getElementById('ic-search-input')?.focus();
    }, 100);
}

/**
 * Close Search Panel
 */
function closeSearchPanel() {
    document.getElementById('ic-search-sidebar').classList.add('collapsed');
}

/**
 * Close all right side panels
 */
function closeAllRightPanels() {
    const panels = ['ic-bookinfo-sidebar', 'ic-settings-sidebar', 'ic-summary-sidebar'];
    panels.forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (panel) panel.classList.add('collapsed');
    });
    IcecreamReader.activeRightPanel = null;
}

/**
 * Toggle Summary Panel (Right Sidebar)
 */
function toggleSummaryPanel() {
    const sidebar = document.getElementById('ic-summary-sidebar');
    const isOpen = !sidebar.classList.contains('collapsed');
    closeAllRightPanels();
    if (isOpen) return; // Was open, now closed by closeAllRightPanels
    sidebar.classList.remove('collapsed');
    IcecreamReader.summaryVisible = true;
    IcecreamReader.activeRightPanel = 'summary';
    checkAIProvider();
}

/**
 * Switch summary tab between chapter and full book
 */
async function switchSummaryTab(tab) {
    const chapterTab = document.getElementById('ic-summary-tab-chapter');
    const bookTab = document.getElementById('ic-summary-tab-book');
    const summaryContainer = document.getElementById('ic-summary-content');
    const genBtn = document.getElementById('ic-generate-btn');
    const genBtnText = document.getElementById('ic-generate-btn-text');

    IcecreamReader.summaryTab = tab;

    if (tab === 'chapter') {
        chapterTab.classList.add('active');
        bookTab.classList.remove('active');
        if (genBtn) genBtn.onclick = () => window.readerApp.generateSummary();
        if (genBtnText) genBtnText.textContent = 'Generate Summary';
        // Try to load cached chapter summary
        summaryContainer.innerHTML = '<div class="ic-loading" style="text-align: center; padding: 40px 20px;"><div class="ic-spinner"></div><p style="margin-top:12px;font-size:12px;color:#999;">Checking for cached summary...</p></div>';
        try {
            const resp = await fetch(`/api/books/${IcecreamReader.bookId}/summary/${IcecreamReader.currentChapter}`);
            if (resp.ok) {
                const data = await resp.json();
                summaryContainer.innerHTML = `
                    <div class="ic-summary-text">
                        <p class="ic-summary-meta">Generated using ${data.provider || 'AI'}</p>
                        ${formatSummaryText(data.summary)}
                    </div>
                `;
                showSummaryActions(true);
                return;
            }
        } catch (e) { /* fall through */ }
        showSummaryActions(false);
        summaryContainer.innerHTML = `
            <div class="ic-summary-empty">
                <p class="ic-summary-empty-text">No summary yet for this chapter.</p>
            </div>
        `;
    } else {
        bookTab.classList.add('active');
        chapterTab.classList.remove('active');
        if (genBtn) genBtn.onclick = () => window.readerApp.generateBookSummary();
        if (genBtnText) genBtnText.textContent = 'Summarize Entire Book';
        // Try to load cached book summary
        summaryContainer.innerHTML = '<div class="ic-loading" style="text-align: center; padding: 40px 20px;"><div class="ic-spinner"></div><p style="margin-top:12px;font-size:12px;color:#999;">Checking for cached summary...</p></div>';
        try {
            const resp = await fetch(`/api/books/${IcecreamReader.bookId}/summary`);
            if (resp.ok) {
                const data = await resp.json();
                summaryContainer.innerHTML = `
                    <div class="ic-summary-text">
                        <p class="ic-summary-meta">Full book summary &bull; Generated using ${data.provider || 'AI'}</p>
                        ${formatSummaryText(data.summary)}
                    </div>
                `;
                showSummaryActions(true);
                return;
            }
        } catch (e) { /* fall through */ }
        showSummaryActions(false);
        summaryContainer.innerHTML = `
            <div class="ic-summary-empty">
                <p class="ic-summary-empty-text">No book summary yet.</p>
            </div>
        `;
    }
}

/**
 * Toggle Book Info Panel (Right Sidebar)
 */
function toggleBookInfoPanel() {
    const sidebar = document.getElementById('ic-bookinfo-sidebar');
    const isOpen = !sidebar.classList.contains('collapsed');
    closeAllRightPanels();
    if (isOpen) return;
    sidebar.classList.remove('collapsed');
    IcecreamReader.activeRightPanel = 'bookinfo';
    loadBookInfo();
}

/**
 * Toggle Settings Panel (Right Sidebar)
 */
function toggleSettingsPanel() {
    const sidebar = document.getElementById('ic-settings-sidebar');
    const isOpen = !sidebar.classList.contains('collapsed');
    closeAllRightPanels();
    if (isOpen) return;
    sidebar.classList.remove('collapsed');
    IcecreamReader.activeRightPanel = 'settings';
}

/**
 * Load Book Info data
 */
async function loadBookInfo() {
    try {
        const response = await fetch(`/api/books/${IcecreamReader.bookId}`);
        if (!response.ok) return;
        const book = await response.json();

        // Update book info elements
        const titleEl = document.getElementById('ic-bookinfo-book-title');
        const authorEl = document.getElementById('ic-bookinfo-author');
        const pagesEl = document.getElementById('ic-bookinfo-pages');
        const chaptersEl = document.getElementById('ic-bookinfo-chapters');
        const progressEl = document.getElementById('ic-bookinfo-progress');
        const coverEl = document.getElementById('ic-cover-image');
        const descEl = document.getElementById('ic-bookinfo-description');

        if (titleEl) titleEl.textContent = book.title || 'Unknown Title';
        if (authorEl) authorEl.textContent = book.author || 'Unknown Author';

        // File path
        const pathEl = document.getElementById('ic-bookinfo-path');
        if (pathEl) pathEl.textContent = book.path || '-';

        const totalPages = book.total_pages || 0;
        const totalChapters = IcecreamReader.totalChapters || 0;
        if (pagesEl) pagesEl.textContent = totalPages || '—';
        if (chaptersEl) chaptersEl.textContent = totalChapters || totalPages || '—';

        // Progress: use book.progress if available, else calculate
        const pct = book.progress
            ? Math.round(book.progress)
            : (totalChapters > 0
                ? Math.round(((IcecreamReader.currentChapter + 1) / totalChapters) * 100)
                : 0);
        if (progressEl) progressEl.textContent = pct + '%';

        // Cover image
        if (coverEl && book.cover_path) {
            coverEl.src = coverUrl(book.cover_path);
        }

        // Build extended info
        const details = [];
        if (book.format) details.push(`<strong>Format:</strong> ${book.format}`);
        if (book.publisher) details.push(`<strong>Publisher:</strong> ${escapeHtml(book.publisher)}`);
        if (book.publish_date) details.push(`<strong>Published:</strong> ${escapeHtml(String(book.publish_date))}`);
        if (book.language) details.push(`<strong>Language:</strong> ${escapeHtml(book.language)}`);
        if (book.isbn) details.push(`<strong>ISBN:</strong> ${escapeHtml(book.isbn)}`);
        if (book.file_size) {
            const mb = (book.file_size / 1048576).toFixed(1);
            details.push(`<strong>File size:</strong> ${mb} MB`);
        }

        // Rating
        const rating = book.rating || 0;
        const starsHtml = [1,2,3,4,5].map(i =>
            `<span class="ic-rating-star ${i <= rating ? 'filled' : ''}" onclick="setReaderRating(${i})">&#9733;</span>`
        ).join('');
        details.push(`<strong>Rating:</strong> <span class="ic-rating-stars">${starsHtml}</span>`);

        // Categories
        if (book.categories && book.categories.length) {
            details.push(`<strong>Categories:</strong> ${book.categories.map(c => escapeHtml(c)).join(', ')}`);
        }

        const descText = book.description || '';
        if (descEl) {
            let html = '';
            if (details.length) html += '<div class="ic-bookinfo-meta">' + details.join('<br>') + '</div>';
            html += descText ? `<p>${escapeHtml(descText)}</p>` : '<p>No description available.</p>';
            descEl.innerHTML = html;
        }
    } catch (error) {
        console.error('Failed to load book info:', error);
    }
}

/**
 * Set rating from reader book info panel
 */
async function setReaderRating(rating) {
    try {
        await fetch(`/api/books/${IcecreamReader.bookId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating })
        });
        loadBookInfo();
    } catch (e) {
        console.error('Failed to save rating:', e);
    }
}

/**
 * Upload cover image from reader book info panel
 */
function uploadReaderCover() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`/api/books/${IcecreamReader.bookId}/cover`, {
                method: 'POST',
                body: formData
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Upload failed');
            }
            const data = await res.json();
            const coverEl = document.getElementById('ic-cover-image');
            if (coverEl) {
                coverEl.src = coverUrl(data.cover_path) + '?t=' + Date.now();
            }
        } catch (e) {
            console.error('Cover upload failed:', e);
        }
    };
    input.click();
}
