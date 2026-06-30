/**
 * Reader: bootstrap.
 *
 * Registers the DOMContentLoaded init sequence, the global event listeners
 * (progress slider, text selection, scroll progress), the keyboard shortcuts,
 * and exposes `initReader` via the `readerApp` object (assigned in globals.js).
 *
 * All DOM-dependent wiring happens inside the DOMContentLoaded callback, by
 * which time every classic reader script has parsed and every function
 * declaration + the IcecreamReader state object are available.
 */

/**
 * Initialize event listeners
 */
function initEventListeners() {
    // Progress slider event listener with tooltip
    const progressSlider = document.getElementById('ic-progress-slider');
    if (progressSlider) {
        // Create tooltip element
        const tooltip = document.createElement('div');
        tooltip.className = 'ic-progress-tooltip';
        tooltip.id = 'ic-progress-tooltip';
        progressSlider.parentNode.appendChild(tooltip);

        progressSlider.addEventListener('input', function (e) {
            const progress = parseFloat(e.target.value);
            const targetChapter = Math.floor((progress / 100) * IcecreamReader.totalChapters);
            if (targetChapter !== IcecreamReader.currentChapter && targetChapter < IcecreamReader.totalChapters) {
                loadChapter(targetChapter);
            }
        });

        progressSlider.addEventListener('mouseenter', function () {
            tooltip.style.opacity = '1';
            updateProgressTooltip(progressSlider, tooltip);
        });

        progressSlider.addEventListener('mousemove', function () {
            updateProgressTooltip(progressSlider, tooltip);
        });

        progressSlider.addEventListener('mouseleave', function () {
            if (!progressSlider.matches(':active')) {
                tooltip.style.opacity = '0';
            }
        });

        progressSlider.addEventListener('mouseup', function () {
            setTimeout(() => { tooltip.style.opacity = '0'; }, 1000);
        });
    }

    // Selection Detection
    document.addEventListener('mouseup', handleTextSelection);

    // Hide menu on click elsewhere
    document.addEventListener('mousedown', function (e) {
        const menu = document.getElementById('ic-selection-menu');
        if (menu && !menu.contains(e.target) && !window.getSelection().toString()) {
            menu.style.display = 'none';
        }
    });

    // Close popups when clicking outside
    document.addEventListener('click', function (e) {
        const popups = ['ic-layout-menu', 'ic-font-size-menu', 'ic-zoom-menu', 'ic-speed-menu', 'ic-settings-menu'];
        const clickedTab = e.target.closest('.ic-tab');
        const clickedPopup = e.target.closest('.ic-popup-menu');

        if (!clickedTab && !clickedPopup) {
            popups.forEach(id => {
                const menu = document.getElementById(id);
                if (menu) menu.style.display = 'none';
            });
        }
    });

    // Scroll progress within chapter (rAF throttled)
    const readingArea = document.getElementById('ic-reading-area');
    if (readingArea) {
        let _scrollTicking = false;
        readingArea.addEventListener('scroll', () => {
            if (!_scrollTicking) {
                requestAnimationFrame(() => {
                    updateScrollProgress();
                    _scrollTicking = false;
                });
                _scrollTicking = true;
            }
        });
    }

    // Load initial annotations and bookmarks
    setTimeout(() => {
        loadAnnotations();
        renderBookmarks();
    }, 500);

}

/**
 * Initialize theme from localStorage
 */
function initTheme() {
    const savedTheme = localStorage.getItem('reader-theme') || 'day';
    setTheme(savedTheme);
}

/**
 * Initialize reader with book data
 */
async function initReader(bookId) {
    IcecreamReader.bookId = bookId;

    try {
        const bookResponse = await fetch(`/api/books/${bookId}`);
        if (!bookResponse.ok) throw new Error('Book not found');
        const book = await bookResponse.json();

        document.getElementById('ic-book-title').textContent = book.title;

        // Populate book info panel
        const titleEl = document.getElementById('ic-bookinfo-book-title');
        const authorEl = document.getElementById('ic-bookinfo-author');
        const pagesEl = document.getElementById('ic-bookinfo-pages');
        const chaptersEl = document.getElementById('ic-bookinfo-chapters');
        const progressEl = document.getElementById('ic-bookinfo-progress');
        const coverEl = document.getElementById('ic-cover-image');
        if (titleEl) titleEl.textContent = book.title;
        if (authorEl) authorEl.textContent = book.author || 'Unknown Author';
        if (pagesEl) pagesEl.textContent = book.total_pages || '-';
        if (chaptersEl) chaptersEl.textContent = book.total_chapters || '-';
        if (progressEl) progressEl.textContent = Math.round(book.progress) + '%';
        if (coverEl && book.cover_path) coverEl.src = coverUrl(book.cover_path);

        // File path
        const pathEl = document.getElementById('ic-bookinfo-path');
        if (pathEl) pathEl.textContent = book.path || '-';

        await initializeTTS();
        await loadTableOfContents(bookId);

        maybeShowCalibreWebTab();

        const startChapter = book.current_chapter || 0;
        await loadChapter(startChapter);

    } catch (error) {
        console.error('Failed to initialize reader:', error);
        const contentArea = document.getElementById('ic-chapter-text');
        contentArea.innerHTML = `
            <div style="text-align: center; padding: 60px 20px; color: #666;">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="#999" style="margin-bottom: 16px;">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                </svg>
                <h3 style="margin-bottom: 8px;">Failed to load book</h3>
                <p style="font-size: 13px; margin-bottom: 20px;">The book file may have been moved or deleted.</p>
                <button onclick="goToLibrary()" style="padding: 8px 20px; background: #4285f4; color: white; border: none; border-radius: 4px; cursor: pointer;">
                    Return to Library
                </button>
            </div>
        `;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    updateZoomDisplay();
    initTheme();
    initReaderPreferences();
    initEventListeners();
    // Restore summary options
    const savedLength = localStorage.getItem('reader-summary-length');
    if (savedLength) {
        document.querySelectorAll('.ic-length-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.length === savedLength);
        });
    }
    const autoSummaryEl = document.getElementById('ic-auto-summary');
    if (autoSummaryEl) {
        autoSummaryEl.checked = localStorage.getItem('reader-auto-summary') === 'true';
    }
});

/* Keyboard shortcuts ------------------------------------------------- */

document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }

    // Ctrl+Shift+B: bookmark the current text selection (falls back to the
    // whole chapter when nothing is selected).
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'B' || e.key === 'b')) {
        e.preventDefault();
        bookmarkSelection();
        return;
    }

    switch (e.key) {
        case 'ArrowLeft':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                if (IcecreamReader.currentChapter > 0) loadChapter(IcecreamReader.currentChapter - 1);
            }
            break;
        case 'ArrowRight':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                const tc = IcecreamReader.totalChapters;
                if (tc <= 0 || IcecreamReader.currentChapter < tc - 1) loadChapter(IcecreamReader.currentChapter + 1);
            }
            break;
        case 'PageUp':
            e.preventDefault();
            if (IcecreamReader.currentChapter > 0) loadChapter(IcecreamReader.currentChapter - 1);
            break;
        case 'PageDown':
            e.preventDefault();
            if (IcecreamReader.totalChapters <= 0 || IcecreamReader.currentChapter < IcecreamReader.totalChapters - 1) loadChapter(IcecreamReader.currentChapter + 1);
            break;
        case 'Home':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                loadChapter(0);
            }
            break;
        case 'End':
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                if (IcecreamReader.totalChapters > 0) loadChapter(IcecreamReader.totalChapters - 1);
            }
            break;
        case '+':
        case '=':
            e.preventDefault();
            adjustZoom(10);
            break;
        case '-':
            e.preventDefault();
            adjustZoom(-10);
            break;
        case 'c':
        case 'C':
            e.preventDefault();
            toggleTOCPanel();
            break;
        case 's':
        case 'S':
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            toggleSummaryPanel();
            break;
        case 't':
        case 'T':
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            toggleTTS();
            break;
        case 'b':
        case 'B':
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            showBookmarksPanel();
            break;
        case 'd':
        case 'D':
            e.preventDefault();
            setTheme('day');
            break;
        case 'n':
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            setTheme('night');
            break;
        case 'f':
        case 'F':
            if (e.ctrlKey || e.metaKey) return;
            e.preventDefault();
            toggleFullscreen();
            break;
        case 'Escape':
            // Close help modal first
            const helpOverlay = document.getElementById('ic-help-overlay');
            if (helpOverlay && helpOverlay.style.display !== 'none') {
                helpOverlay.style.display = 'none';
                break;
            }
            // Close all panels and popups
            closeAllRightPanels();
            closeAllLeftPanels();
            hideOtherMenus('');
            break;
        case '?':
            e.preventDefault();
            toggleHelpModal();
            break;
    }
});
