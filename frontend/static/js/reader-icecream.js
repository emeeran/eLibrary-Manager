/**
 * Icecream eBook Reader - JavaScript Controller
 * Handles all reader functionality matching Icecream eBook Reader Pro UI
 *
 * Performance Optimizations:
 * - Client-side chapter caching (Map)
 * - Bidirectional prefetching (prev + next chapters)
 * - Debounced progress saving
 * - requestIdleCallback for non-critical work
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
    fontSize: 16,
    lineHeight: 1.8,
    // Volume
    volume: 80,
    // Right panel state
    activeRightPanel: null, // 'bookinfo', 'settings', 'summary', or null
    // TTS State
    ttsEnabled: false,
    ttsPlaying: false,
    ttsVoices: [],
    ttsCurrentVoice: null,
    ttsRate: 1.0,
    ttsAudio: null,
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
        if (coverEl && book.cover_path) coverEl.src = book.cover_path;

        // File path
        const pathEl = document.getElementById('ic-bookinfo-path');
        if (pathEl) pathEl.textContent = book.path || '-';

        await initializeTTS();
        await loadTableOfContents(bookId);

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

/**
 * Load table of contents with expandable sections
 */
async function loadTableOfContents(bookId) {
    const tocContainer = document.getElementById('ic-toc-content');

    try {
        const response = await fetch(`/api/books/${bookId}/toc`);
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.message || 'Failed to load TOC');
        }
        const data = await response.json();

        IcecreamReader.totalChapters = data.total_chapters;
        const totalChaptersEl = document.getElementById('ic-total-pages');
        if (totalChaptersEl) {
            totalChaptersEl.textContent = data.total_chapters;
        }

        if (data.items && data.items.length > 0) {
            IcecreamReader.chapters = data.items;
            renderTableOfContentsWithSections(data.items);
        } else {
            generateChapterList(data.total_chapters);
        }

    } catch (error) {
        console.error('Failed to load TOC:', error);
        generateChapterList(IcecreamReader.totalChapters || 10);
    }
}

/**
 * Render table of contents with expandable sections
 */
function renderTableOfContentsWithSections(items) {
    const tocContainer = document.getElementById('ic-toc-content');
    if (!tocContainer) return;

    let html = '';
    let currentSection = null;

    // Build page-start lookup keyed by actual chapter index
    let pageAccum = 1;
    const pageStartsByChapterIdx = {};
    for (const item of items) {
        const chIdx = item.index;
        if (chIdx !== undefined && !(chIdx in pageStartsByChapterIdx)) {
            pageStartsByChapterIdx[chIdx] = pageAccum;
        }
        pageAccum += IcecreamReader.chapterPageCounts[item.index] || 1;
    }

    items.forEach((item, displayIdx) => {
        const chIdx = item.index !== undefined ? item.index : displayIdx;
        const isActive = chIdx === IcecreamReader.currentChapter;
        const pageLabel = pageStartsByChapterIdx[chIdx] ? `p.${pageStartsByChapterIdx[chIdx]}` : '';

        // Check if this is a section header (Part, Chapter, etc.)
        if (item.level === 1 || (item.title && /^(Part|Chapter|Book|Section)\s/i.test(item.title))) {
            if (currentSection) {
                html += '</div></div>'; // Close previous section
            }

            const sectionId = `section-${displayIdx}`;
            html += `
                <div class="ic-toc-section" id="${sectionId}">
                    <div class="ic-toc-section-header ${isActive ? 'active' : ''}" data-index="${chIdx}">
                        <span class="ic-chapter-number">${chIdx + 1}.</span>
                        <span class="ic-toc-section-title" onclick="goToChapter(${chIdx})">${escapeHtml(item.title || `Section ${chIdx + 1}`)}</span>
                        <span class="ic-chapter-page">${pageLabel}</span>
                        <svg class="ic-chevron" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" onclick="toggleTOCSection('${sectionId}')">
                            <path d="M7 10l5 5 5-5z"/>
                        </svg>
                    </div>
                    <div class="ic-toc-section-content">
            `;
            currentSection = sectionId;
        } else {
            // Regular chapter item
            const indent = item.level > 1 ? 'style="padding-left: ' + (16 + item.level * 12) + 'px"' : '';
            html += `
                <div class="ic-chapter-item ${isActive ? 'active' : ''}"
                     id="toc-item-${chIdx}"
                     data-index="${chIdx}"
                     onclick="goToChapter(${chIdx})"
                     ${indent}>
                    <span class="ic-chapter-number">${chIdx + 1}.</span>
                    <span class="ic-chapter-name">${escapeHtml(item.title || 'Chapter ' + (chIdx + 1))}</span>
                    <span class="ic-chapter-page">${pageLabel}</span>
                </div>
            `;
        }
    });

    if (currentSection) {
        html += '</div></div>'; // Close last section
    }

    tocContainer.innerHTML = html;
    updateTOCHighlight(IcecreamReader.currentChapter);
}

/**
 * Toggle TOC section expand/collapse
 */
function toggleTOCSection(sectionId) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.classList.toggle('collapsed');
    }
}

/**
 * Efficiently update TOC highlight without re-rendering everything
 */
function updateTOCHighlight(activeIndex) {
    // Clear active from all items
    document.querySelectorAll('.ic-chapter-item.active, .ic-toc-section-header.active').forEach(item => {
        item.classList.remove('active');
    });

    // Highlight by data-index attribute (matches actual chapter index)
    const activeItem = document.querySelector(`.ic-chapter-item[data-index="${activeIndex}"]`);
    if (activeItem) {
        activeItem.classList.add('active');
        activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        return;
    }

    // Try section headers
    const activeHeader = document.querySelector(`.ic-toc-section-header[data-index="${activeIndex}"]`);
    if (activeHeader) {
        activeHeader.classList.add('active');
        activeHeader.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Highlight section header (for items that are section headers with data-index)
    const sectionHeader = document.querySelector(`.ic-toc-section-header[data-index="${activeIndex}"]`);
    if (sectionHeader) {
        sectionHeader.classList.add('active');
        // Expand the parent section
        const section = sectionHeader.closest('.ic-toc-section');
        if (section) {
            section.classList.remove('collapsed');
        }
        sectionHeader.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

/**
 * Generate fallback chapter list
 */
function generateChapterList(total) {
    const items = [];
    for (let i = 0; i < total; i++) {
        items.push({ index: i, title: `Chapter ${i + 1}`, level: 1 });
    }
    IcecreamReader.chapters = items;
    renderTableOfContentsWithSections(items);
}

/**
 * Load a specific chapter
 */
async function loadChapter(chapterIndex) {
    if (chapterIndex < 0 || (IcecreamReader.totalChapters > 0 && chapterIndex >= IcecreamReader.totalChapters)) {
        return;
    }

    // Reset continuous scroll state when explicitly navigating
    if (IcecreamReader.pageLayout === 'continuous') {
        IcecreamReader._continuousRendered = new Set([chapterIndex]);
    }

    if (IcecreamReader.chapterCache.has(chapterIndex)) {
        const cached = IcecreamReader.chapterCache.get(chapterIndex);
        cached.timestamp = Date.now();
        renderChapterData(chapterIndex, cached.data, cached.html, true);
        prefetchAdjacentChapters(chapterIndex);
        return;
    }

    if (IcecreamReader.loading) return;
    IcecreamReader.loading = true;

    const contentArea = document.getElementById('ic-chapter-text');
    contentArea.innerHTML = '<div class="ic-loading ic-loading-fast"><div class="ic-spinner"></div></div>';

    try {
        const response = await fetch(
            `/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`,
            { cache: 'no-cache' }
        );
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.message || 'Failed to load chapter');
        }
        const data = await response.json();

        const formattedHtml = formatChapterContent(data.content);

        IcecreamReader.chapterCache.set(chapterIndex, {
            data: data,
            html: formattedHtml,
            timestamp: Date.now()
        });

        renderChapterData(chapterIndex, data, formattedHtml);
        prefetchAdjacentChapters(chapterIndex);

    } catch (error) {
        console.error('Failed to load chapter:', error);
        showError('Failed to load chapter. Please try again.');
    } finally {
        IcecreamReader.loading = false;
    }
}

/**
 * Common rendering logic for both fresh and cached loads
 */
function renderChapterData(chapterIndex, data, formattedHtml, isCached = false) {
    const contentArea = document.getElementById('ic-chapter-text');

    IcecreamReader.currentChapter = chapterIndex;
    if (data.total_chapters) {
        IcecreamReader.totalChapters = data.total_chapters;
    }

    // Track estimated pages per chapter for real page numbers
    if (data.estimated_pages) {
        IcecreamReader.chapterPageCounts[chapterIndex] = data.estimated_pages;
    }

    const totalChaptersEl = document.getElementById('ic-total-pages');
    if (totalChaptersEl) {
        // Calculate total pages from estimated pages, fallback to 1 per chapter
        let total = 0;
        for (let i = 0; i < IcecreamReader.totalChapters; i++) {
            total += IcecreamReader.chapterPageCounts[i] || 1;
        }
        totalChaptersEl.textContent = Math.max(total, IcecreamReader.totalChapters);
    }

    const displayTitle = data.title || '';
    const isGeneric = !displayTitle || /^Page \d+$/i.test(displayTitle) || displayTitle === 'Untitled Chapter';

    const chapterTitleEl = document.getElementById('ic-chapter-title');
    if (chapterTitleEl) {
        if (!isGeneric) {
            chapterTitleEl.textContent = displayTitle;
            chapterTitleEl.style.display = 'block';
        } else {
            chapterTitleEl.style.display = 'none';
        }
    }

    // Update footer chapter title
    const footerTitle = document.getElementById('ic-footer-chapter-title');
    if (footerTitle) {
        footerTitle.textContent = isGeneric ? '' : displayTitle;
    }

    contentArea.innerHTML = formattedHtml;

    // Remove duplicate heading from chapter content that matches the UI chapter title
    if (displayTitle && !isGeneric) {
        removeDuplicateHeading(contentArea, displayTitle);
    }

    if (isCached) {
        contentArea.classList.add('ic-cached');
        setTimeout(() => contentArea.classList.remove('ic-cached'), 150);
    } else {
        contentArea.classList.add('ic-loaded');
        setTimeout(() => contentArea.classList.remove('ic-loaded'), 250);
    }

    updateTOCHighlight(chapterIndex);
    updateProgress();
    updateNavButtons();
    saveProgress(chapterIndex);

    // Re-apply persisted highlights from API for this chapter
    loadAnnotations();

    const readingArea = document.getElementById('ic-reading-area');
    if (readingArea) {
        readingArea.scrollTop = 0;
    }

    updateScrollProgress();
}

/**
 * Prefetch adjacent chapters for instant navigation
 */
function prefetchAdjacentChapters(currentIndex) {
    const chaptersToFetch = [];

    const nextIndex = currentIndex + 1;
    if (nextIndex < IcecreamReader.totalChapters && !IcecreamReader.chapterCache.has(nextIndex)) {
        chaptersToFetch.push(nextIndex);
    }

    const prevIndex = currentIndex - 1;
    if (prevIndex >= 0 && !IcecreamReader.chapterCache.has(prevIndex)) {
        chaptersToFetch.push(prevIndex);
    }

    if (chaptersToFetch.length === 0) return;

    const scheduleWork = window.requestIdleCallback || ((cb) => setTimeout(cb, 100));

    scheduleWork(() => {
        chaptersToFetch.forEach((chapterIndex, i) => {
            setTimeout(() => prefetchChapter(chapterIndex), i * 200);
        });
    }, { timeout: 2000 });
}

/**
 * Prefetch a single chapter in the background
 */
async function prefetchChapter(chapterIndex) {
    if (IcecreamReader.chapterCache.has(chapterIndex) || IcecreamReader.isPrefetching) {
        return;
    }

    IcecreamReader.isPrefetching = true;

    try {
        const response = await fetch(
            `/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`
        );

        if (response.ok) {
            const data = await response.json();
            const formattedHtml = formatChapterContent(data.content);

            IcecreamReader.chapterCache.set(chapterIndex, {
                data: data,
                html: formattedHtml,
                timestamp: Date.now()
            });

            evictOldCacheEntries();
        }
    } catch (e) {
        console.warn('[Prefetch] Background fetch failed', e);
    } finally {
        IcecreamReader.isPrefetching = false;
    }
}

/**
 * Evict oldest cache entries when cache exceeds max size
 */
function evictOldCacheEntries() {
    if (IcecreamReader.chapterCache.size <= IcecreamReader.maxCacheSize) {
        return;
    }

    const entries = Array.from(IcecreamReader.chapterCache.entries())
        .sort((a, b) => a[1].timestamp - b[1].timestamp);

    while (entries.length > IcecreamReader.maxCacheSize) {
        const [key] = entries.shift();
        IcecreamReader.chapterCache.delete(key);
    }
}

/**
 * Remove duplicate heading from chapter content that matches the chapter title.
 * Compares with all whitespace stripped to handle spacing differences.
 */
function removeDuplicateHeading(container, chapterTitle) {
    if (!chapterTitle) return;
    const firstHeading = container.querySelector('h1, h2, h3');
    if (!firstHeading) return;
    const normalize = (str) => str.replace(/\s+/g, '').toLowerCase();
    const headingNorm = normalize(firstHeading.textContent);
    const titleNorm = normalize(chapterTitle);
    if (headingNorm === titleNorm || headingNorm.includes(titleNorm) || titleNorm.includes(headingNorm)) {
        firstHeading.remove();
    }
}

/**
 * Format chapter content for display
 */
function formatChapterContent(content) {
    if (!content) return '<p class="empty-content">No content available.</p>';

    content = content.trim();

    if (content.startsWith('<') && (content.includes('<p>') || content.includes('<div') || content.includes('pdf-page'))) {
        return content;
    }

    const lines = content.replace(/\r\n/g, '\n').split('\n');
    const blocks = [];
    let currentParagraph = [];

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();

        if (!line) {
            if (currentParagraph.length > 0) {
                const text = currentParagraph.join(' ').trim();
                if (text) {
                    blocks.push({ type: 'paragraph', content: text });
                }
                currentParagraph = [];
            }
            continue;
        }

        const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
        if (headingMatch) {
            if (currentParagraph.length > 0) {
                const text = currentParagraph.join(' ').trim();
                if (text) blocks.push({ type: 'paragraph', content: text });
                currentParagraph = [];
            }
            blocks.push({ type: 'heading', level: headingMatch[1].length, content: headingMatch[2] });
            continue;
        }

        currentParagraph.push(line);
    }

    if (currentParagraph.length > 0) {
        const text = currentParagraph.join(' ').trim();
        if (text) blocks.push({ type: 'paragraph', content: text });
    }

    return blocks.map((block, index) => {
        switch (block.type) {
            case 'heading':
                return `<h${block.level}>${formatInlineText(block.content)}</h${block.level}>`;
            case 'paragraph':
                return `<p>${formatInlineText(block.content)}</p>`;
            default:
                return '';
        }
    }).join('\n');
}

/**
 * Format inline text with bold, italic, links, etc.
 */
function formatInlineText(text) {
    if (!text) return '';

    let result = escapeHtml(text);

    result = result.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    result = result.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    result = result.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
    result = result.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    return result;
}

/**
 * Go to specific chapter
 */
function goToChapter(index) {
    if (index >= 0 && (IcecreamReader.totalChapters <= 0 || index < IcecreamReader.totalChapters)) {
        loadChapter(index);
    }
}

/**
 * Update reading progress with real page numbers
 */
function updateProgress() {
    const progress = ((IcecreamReader.currentChapter + 1) / IcecreamReader.totalChapters) * 100;

    const progressSlider = document.getElementById('ic-progress-slider');
    if (progressSlider) {
        progressSlider.value = progress;
    }

    const pageNumberEl = document.getElementById('ic-page-number');
    const totalPagesEl = document.getElementById('ic-total-pages');

    // Calculate real page numbers from estimated pages per chapter
    // Default to 1 page per chapter (PDFs where chapter = page)
    let currentPage = 1;
    let totalPages = 0;

    for (let i = 0; i < IcecreamReader.totalChapters; i++) {
        const pages = IcecreamReader.chapterPageCounts[i] || 1;
        if (i === IcecreamReader.currentChapter) {
            currentPage = totalPages + 1;
        }
        totalPages += pages;
    }

    if (pageNumberEl) {
        const chapterPages = IcecreamReader.chapterPageCounts[IcecreamReader.currentChapter] || 1;
        const endPage = currentPage + chapterPages - 1;
        pageNumberEl.textContent = chapterPages > 1 ? `${currentPage}-${endPage}` : `${currentPage}`;
    }

    if (totalPagesEl) {
        totalPagesEl.textContent = totalPages;
    }
}

/**
 * Update prev/next navigation buttons
 */
function updateNavButtons() {
    const prevBtn = document.getElementById('ic-prev-btn');
    const nextBtn = document.getElementById('ic-next-btn');
    const navInfo = document.getElementById('ic-nav-info');

    if (prevBtn) {
        prevBtn.disabled = IcecreamReader.currentChapter <= 0;
    }
    if (nextBtn) {
        nextBtn.disabled = IcecreamReader.currentChapter >= IcecreamReader.totalChapters - 1;
    }
    if (navInfo) {
        navInfo.textContent = `${IcecreamReader.currentChapter + 1} / ${IcecreamReader.totalChapters}`;
    }
}

/**
 * Save reading progress (debounced)
 */
function saveProgress(chapterIndex) {
    if (IcecreamReader.progressSaveTimeout) {
        clearTimeout(IcecreamReader.progressSaveTimeout);
    }

    IcecreamReader.progressSaveTimeout = setTimeout(() => {
        saveProgressNow(chapterIndex);
    }, IcecreamReader.progressSaveDelay);
}

/**
 * Actually save progress to server
 */
async function saveProgressNow(chapterIndex) {
    try {
        const data = JSON.stringify({
            chapter_index: chapterIndex,
            progress: ((chapterIndex + 1) / IcecreamReader.totalChapters) * 100
        });

        const url = `/api/books/${IcecreamReader.bookId}/progress`;

        if (navigator.sendBeacon) {
            const blob = new Blob([data], { type: 'application/json' });
            navigator.sendBeacon(url, blob);
        } else {
            await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: data
            });
        }
    } catch (error) {
        console.error('Failed to save progress:', error);
    }
}

// Save progress on page unload
window.addEventListener('beforeunload', () => {
    if (IcecreamReader.progressSaveTimeout) {
        clearTimeout(IcecreamReader.progressSaveTimeout);
        saveProgressNow(IcecreamReader.currentChapter);
    }
});

/* ========================================
   PANEL MANAGEMENT
   ======================================== */

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
 * Toggle Volume Control (Inline in tabs)
 */
function toggleVolumeControl() {
    const volumeControl = document.getElementById('ic-volume-control');
    if (volumeControl) {
        const isVisible = volumeControl.style.display !== 'none';
        volumeControl.style.display = isVisible ? 'none' : 'flex';
    }
}

/**
 * Set Volume
 */
function setVolume(value) {
    value = parseInt(value);
    IcecreamReader.volume = value;
    localStorage.setItem('reader-volume', value);

    // Update both volume sliders if they exist
    const inlineSlider = document.getElementById('ic-volume-slider');
    const sidebarSlider = document.getElementById('ic-volume-slider-sidebar');
    if (inlineSlider) inlineSlider.value = value;
    if (sidebarSlider) sidebarSlider.value = value;

    // Update TTS audio volume if playing
    if (IcecreamReader.ttsAudio) {
        IcecreamReader.ttsAudio.volume = value / 100;
    }
}

/**
 * Set Font Family
 */
function setFontFamily(fontFamily) {
    const contentArea = document.querySelector('.ic-chapter-text');
    if (!contentArea) return;

    let fontStack = 'Georgia, "Times New Roman", serif'; // default
    switch (fontFamily) {
        case 'georgia':
            fontStack = 'Georgia, serif';
            break;
        case 'times':
            fontStack = 'Times New Roman, Times, serif';
            break;
        case 'arial':
            fontStack = 'Arial, Helvetica, sans-serif';
            break;
        case 'verdana':
            fontStack = 'Verdana, Geneva, sans-serif';
            break;
        case 'original':
        default:
            fontStack = 'Georgia, "Times New Roman", serif';
            break;
    }

    contentArea.style.fontFamily = fontStack;
    localStorage.setItem('reader-font-family', fontFamily);
    syncSettingsToServer();
}

/**
 * Adjust Line Spacing
 */
function adjustLineSpacing(delta) {
    const current = Math.round(IcecreamReader.lineHeight * 10);
    const newVal = Math.max(10, Math.min(30, current + (delta * 1)));
    setLineSpacing(newVal);
}

/**
 * Set line spacing from slider value (10-30 maps to 1.0-3.0)
 */
function setLineSpacing(sliderVal) {
    sliderVal = parseInt(sliderVal);
    const lineHeight = sliderVal / 10;
    IcecreamReader.lineHeight = lineHeight;
    localStorage.setItem('reader-line-height', lineHeight);

    // Apply to all chapter text elements
    document.querySelectorAll('.ic-chapter-text').forEach(el => {
        el.style.setProperty('line-height', lineHeight.toString(), 'important');
    });

    // Also apply to reading area paragraphs for consistent spacing
    document.querySelectorAll('.ic-chapter-text p').forEach(p => {
        p.style.lineHeight = lineHeight.toString();
    });

    // Update slider
    const slider = document.getElementById('ic-line-spacing-slider-sidebar');
    if (slider) slider.value = sliderVal;

    // Update display
    const display = document.getElementById('ic-line-spacing-value');
    if (display) display.textContent = lineHeight.toFixed(1);
    syncSettingsToServer();
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
            coverEl.src = book.cover_path.startsWith('/') ? book.cover_path : '/covers/' + book.cover_path;
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
                coverEl.src = `/covers/${data.cover_path}?t=${Date.now()}`;
            }
        } catch (e) {
            console.error('Cover upload failed:', e);
        }
    };
    input.click();
}

/* ========================================
   SEARCH FUNCTIONALITY
   ======================================== */

let searchTimeout = null;

/**
 * Handle search input
 */
function handleSearch(event) {
    const query = event.target.value.trim();
    const clearBtn = document.getElementById('ic-search-clear');

    if (clearBtn) {
        clearBtn.style.display = query ? 'flex' : 'none';
    }

    clearTimeout(searchTimeout);

    if (query.length < 2) {
        document.getElementById('ic-search-results').innerHTML = `
            <div class="ic-sidebar-empty">
                <div class="ic-sidebar-empty-icon">${EmptyStateIcons.search}</div>
                <div class="ic-sidebar-empty-text">Keep typing...</div>
                <div class="ic-sidebar-empty-hint">Enter at least 2 characters to search</div>
            </div>`;
        return;
    }

    searchTimeout = setTimeout(() => {
        performSearch(query);
    }, 300);
}

/**
 * Perform search
 */
async function performSearch(query) {
    const resultsContainer = document.getElementById('ic-search-results');
    resultsContainer.innerHTML = '<div class="ic-loading">Searching...</div>';

    try {
        const response = await fetch(`/api/books/${IcecreamReader.bookId}/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('Search failed');

        const results = await response.json();
        displaySearchResults(results, query);
    } catch (error) {
        console.error('Search error:', error);
        resultsContainer.innerHTML = '<div class="ic-sidebar-empty">Search failed. Please try again.</div>';
    }
}

/**
 * Display search results
 */
function displaySearchResults(results, query) {
    const container = document.getElementById('ic-search-results');

    if (!results || results.length === 0) {
        container.innerHTML = '<div class="ic-sidebar-empty">No results found.</div>';
        return;
    }

    container.innerHTML = results.map(result => `
        <div class="ic-search-result-item" onclick="loadChapter(${result.chapter})">
            <div class="ic-search-result-title">${escapeHtml(result.title || `Chapter ${result.chapter + 1}`)}</div>
            <div class="ic-search-result-excerpt">${highlightSearchTerm(result.excerpt || '', query)}</div>
        </div>
    `).join('');
}

/**
 * Highlight search term in text
 */
function highlightSearchTerm(text, term) {
    const regex = new RegExp(`(${escapeRegex(term)})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

/**
 * Clear search
 */
function clearSearch() {
    const input = document.getElementById('ic-search-input');
    const clearBtn = document.getElementById('ic-search-clear');
    const results = document.getElementById('ic-search-results');

    if (input) input.value = '';
    if (clearBtn) clearBtn.style.display = 'none';
    if (results) results.innerHTML = `
        <div class="ic-sidebar-empty">
            <div class="ic-sidebar-empty-icon">${EmptyStateIcons.search}</div>
            <div class="ic-sidebar-empty-text">Search this book</div>
            <div class="ic-sidebar-empty-hint">Enter at least 2 characters to search</div>
        </div>`;
}

/* ========================================
   THEME & SETTINGS
   ======================================== */

/**
 * Set theme (day/sepia/night/sepia-light/sepia-dark)
 */
function setTheme(theme) {
    IcecreamReader.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('reader-theme', theme);
    syncSettingsToServer();

    // Handle sepia variants
    if (theme === 'sepia-light' || theme === 'sepia-dark') {
        // Update sepia radio buttons
        document.querySelectorAll('.ic-sepia-option input').forEach(radio => {
            radio.checked = radio.value === theme.replace('sepia-', '');
        });
        // Unset Day/Night buttons
        document.querySelectorAll('.ic-theme-toggle-btn').forEach(btn => {
            btn.classList.remove('active');
        });
    } else {
        // Update Day/Night button states
        document.querySelectorAll('.ic-theme-toggle-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.theme === theme) {
                btn.classList.add('active');
            }
        });
        // Unset sepia radios
        document.querySelectorAll('.ic-sepia-option input').forEach(radio => {
            radio.checked = false;
        });
    }

    // Update old-style theme buttons (if any)
    document.querySelectorAll('.ic-theme-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.theme === theme) {
            btn.classList.add('active');
        }
    });
}

/* ========================================
   ZOOM & FONT SIZE
   ======================================== */

/**
 * Set zoom level
 */
function setZoom(value) {
    value = parseInt(value);
    IcecreamReader.zoomLevel = value;
    localStorage.setItem('reader-zoom', value);

    const content = document.querySelector('.ic-chapter-content');
    if (content) {
        const scale = value / 100;
        
        // Use CSS zoom property where supported (layout-friendly)
        if ('zoom' in document.body.style && !navigator.userAgent.includes('Firefox')) {
            content.style.zoom = scale;
            content.style.transform = '';
            content.style.transformOrigin = '';
        } else {
            // Fallback for Firefox (or browsers without zoom support)
            content.style.transform = `scale(${scale})`;
            content.style.transformOrigin = 'top center';
            
            // Adjust margin to account for scaled height and avoid overlapping footer
            if (scale > 1) {
                const extraHeight = (content.offsetHeight * (scale - 1));
                content.style.marginBottom = `${extraHeight + 60}px`;
            } else {
                content.style.marginBottom = '60px';
            }
        }
    }

    // Update both display formats
    const display = document.getElementById('ic-zoom-display');
    const inlineDisplay = document.getElementById('ic-zoom-inline');
    const zoomValue = (value / 100).toFixed(1) + 'x';

    if (display) {
        display.textContent = value + '%';
    }
    if (inlineDisplay) {
        inlineDisplay.textContent = zoomValue;
    }

    const slider = document.getElementById('ic-zoom-slider');
    if (slider) {
        slider.value = value;
    }

    const menu = document.getElementById('ic-zoom-menu');
    if (menu) menu.style.display = 'none';
}

/**
 * Adjust zoom by delta
 */
function adjustZoom(delta) {
    const newZoom = Math.max(50, Math.min(200, IcecreamReader.zoomLevel + delta));
    setZoom(newZoom);
}

/**
 * Set font size
 */
function setFontSize(size) {
    size = parseInt(size);
    IcecreamReader.fontSize = size;
    localStorage.setItem('reader-font-size', size);
    syncSettingsToServer();

    const contentArea = document.querySelector('.ic-chapter-text');
    if (contentArea) {
        contentArea.style.fontSize = `${size}px`;
    }

    const display = document.getElementById('ic-font-size-display');
    if (display) {
        display.textContent = 'A';
        display.style.fontSize = `${Math.min(size / 16 * 16, 18)}px`;
    }

    // Update both sliders
    const slider = document.getElementById('ic-font-size-slider');
    const sidebarSlider = document.getElementById('ic-font-size-slider-sidebar');
    if (slider) slider.value = size;
    if (sidebarSlider) sidebarSlider.value = size;

    // Update the font size value display
    const valueDisplay = document.getElementById('ic-font-size-value');
    if (valueDisplay) {
        valueDisplay.textContent = size + 'px';
    }
}

/**
 * Adjust font size by delta
 */
function adjustFontSize(delta) {
    const newSize = Math.max(12, Math.min(24, IcecreamReader.fontSize + delta));
    setFontSize(newSize);
}

/* ========================================
   SPEED & TTS
   ======================================== */

/**
 * Set TTS speed
 */
function setSpeed(rate) {
    IcecreamReader.ttsRate = rate;

    const display = document.getElementById('ic-speed-display');
    if (display) {
        display.textContent = rate.toFixed(1) + 'x';
    }

    if (IcecreamReader.ttsAudio) {
        IcecreamReader.ttsAudio.playbackRate = rate;
    }

    if (IcecreamReader.ttsPlaying) {
        stopTTS();
        setTimeout(() => startTTS(), 100);
    }

    localStorage.setItem('tts-speed', rate);

    const menu = document.getElementById('ic-speed-menu');
    if (menu) menu.style.display = 'none';
}

/**
 * Initialize TTS voices
 */
async function initializeTTS() {
    try {
        const response = await fetch('/api/tts/voices');
        if (!response.ok) return;

        const data = await response.json();
        IcecreamReader.ttsVoices = data.voices || [];
        IcecreamReader.ttsCurrentVoice = data.default_voice || 'en';
    } catch (error) {
        console.error('Failed to load TTS voices:', error);
    }
}

/**
 * Toggle TTS on/off
 */
async function toggleTTS() {
    if (IcecreamReader.ttsPlaying) {
        stopTTS();
    } else {
        await startTTS();
    }
}

/**
 * Start TTS playback
 */
async function startTTS() {
    const chapterText = document.getElementById('ic-chapter-text');
    if (!chapterText) return;

    const text = chapterText.innerText || chapterText.textContent;
    if (!text || text.trim().length < 10) {
        showToast('No content to read');
        return;
    }

    try {
        IcecreamReader.ttsEnabled = true;
        IcecreamReader.ttsPlaying = true;
        updateTTSUI();

        const cleanText = text.replace(/\s+/g, ' ').trim();

        const response = await fetch('/api/tts/synthesize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: cleanText,
                voice: IcecreamReader.ttsCurrentVoice,
                rate: IcecreamReader.ttsRate.toString()
            })
        });

        if (!response.ok) {
            throw new Error('TTS synthesis failed');
        }

        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);

        if (IcecreamReader.ttsAudio) {
            IcecreamReader.ttsAudio.pause();
            IcecreamReader.ttsAudio = null;
        }

        IcecreamReader.ttsAudio = new Audio(audioUrl);
        IcecreamReader.ttsAudio.onended = () => {
            stopTTS();
        };
        IcecreamReader.ttsAudio.onerror = () => {
            stopTTS();
            showToast('Audio playback error. Please try again.');
        };

        await IcecreamReader.ttsAudio.play();

    } catch (error) {
        console.error('TTS error:', error);
        stopTTS();
        showToast(`Failed to play audio: ${error.message}`);
    }
}

/**
 * Stop TTS playback
 */
function stopTTS() {
    if (IcecreamReader.ttsAudio) {
        IcecreamReader.ttsAudio.pause();
        IcecreamReader.ttsAudio = null;
    }

    IcecreamReader.ttsPlaying = false;
    updateTTSUI();
}

/**
 * Update TTS UI state
 */
function updateTTSUI() {
    const toggleBtn = document.getElementById('ic-tts-toggle');

    if (IcecreamReader.ttsEnabled || IcecreamReader.ttsPlaying) {
        toggleBtn.classList.add('ic-tts-active');

        if (IcecreamReader.ttsPlaying) {
            document.body.classList.add('ic-tts-playing');
        } else {
            document.body.classList.remove('ic-tts-playing');
        }
    } else {
        toggleBtn.classList.remove('ic-tts-active');
        document.body.classList.remove('ic-tts-playing');
    }
}

/* ========================================
   PAGE LAYOUT
   ======================================== */

/**
 * Set page layout mode
 */
function setPageLayout(layout) {
    IcecreamReader.pageLayout = layout;
    localStorage.setItem('reader-page-layout', layout);

    const contentArea = document.getElementById('ic-chapter-content');
    if (!contentArea) return;

    contentArea.classList.remove('layout-single', 'layout-double', 'layout-continuous');
    contentArea.classList.add(`layout-${layout}`);

    // Setup or teardown continuous scroll (rAF throttled)
    const readingArea = document.getElementById('ic-reading-area');
    if (readingArea) {
        readingArea.removeEventListener('scroll', handleContinuousScroll);
        if (layout === 'continuous') {
            let _contScrollTicking = false;
            const throttledHandler = (e) => {
                if (!_contScrollTicking) {
                    requestAnimationFrame(() => {
                        handleContinuousScroll(e);
                        _contScrollTicking = false;
                    });
                    _contScrollTicking = true;
                }
            };
            readingArea.addEventListener('scroll', throttledHandler);
            IcecreamReader._continuousRendered = new Set([IcecreamReader.currentChapter]);
        }
    }

    // Update page view buttons in settings panel
    document.querySelectorAll('.ic-page-view-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.layout === layout) {
            btn.classList.add('active');
        }
    });

    const menu = document.getElementById('ic-layout-menu');
    if (menu) menu.style.display = 'none';

    const layoutNames = {
        'single': 'Single Page',
        'double': 'Double Page',
        'continuous': 'Continuous Scroll'
    };
    showToast(`Layout: ${layoutNames[layout]}`);
    syncSettingsToServer();
}
/**
 * Handle continuous scroll (throttled)
 */
let _continuousScrollTimer = null;
function handleContinuousScroll() {
    if (IcecreamReader.pageLayout !== 'continuous') return;
    if (_continuousScrollTimer) return; // Throttle: skip if already pending
    _continuousScrollTimer = setTimeout(() => { _continuousScrollTimer = null; }, 200);

    const readingArea = document.getElementById('ic-reading-area');
    const contentArea = document.getElementById('ic-chapter-text');
    if (!readingArea || !contentArea) return;

    const scrollBottom = readingArea.scrollTop + readingArea.clientHeight;
    const scrollHeight = readingArea.scrollHeight;

    // Load next chapter when near bottom
    if (scrollBottom > scrollHeight - 500) {
        const nextChapter = IcecreamReader.currentChapter + 1;
        if (nextChapter < IcecreamReader.totalChapters) {
            appendChapter(nextChapter); // Don't await — fire and forget
        }
    }

    // Load prev chapter when near top
    if (readingArea.scrollTop < 300) {
        if (IcecreamReader._continuousRendered) {
            const rendered = Array.from(IcecreamReader._continuousRendered).sort((a, b) => a - b);
            const firstRendered = rendered[0];
            if (firstRendered > 0) {
                prependChapter(firstRendered - 1); // Don't await
            }
        }
    }
}

/**
 * Append a chapter to the continuous scroll content
 */
async function appendChapter(chapterIndex) {
    if (!IcecreamReader._continuousRendered) IcecreamReader._continuousRendered = new Set();
    if (IcecreamReader._continuousRendered.has(chapterIndex)) return;

    try {
        const response = await fetch(`/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`);
        if (!response.ok) return;
        const data = await response.json();
        const formattedHtml = formatChapterContent(data.content);

        // Cache the chapter
        IcecreamReader.chapterCache.set(chapterIndex, {
            data: data,
            html: formattedHtml,
            timestamp: Date.now()
        });
        if (data.estimated_pages) {
            IcecreamReader.chapterPageCounts[chapterIndex] = data.estimated_pages;
        }

        const contentArea = document.getElementById('ic-chapter-text');
        if (!contentArea) return;

        // Add chapter divider
        const divider = document.createElement('div');
        divider.className = 'ic-chapter-divider';
        divider.dataset.chapterIndex = chapterIndex;
        divider.innerHTML = `<h3 class="ic-chapter-divider-title">${escapeHtml(data.title || 'Chapter ' + (chapterIndex + 1))}</h3>`;
        contentArea.appendChild(divider);

        // Add chapter content
        const chapterDiv = document.createElement('div');
        chapterDiv.className = 'ic-continuous-chapter';
        chapterDiv.dataset.chapterIndex = chapterIndex;
        chapterDiv.innerHTML = formattedHtml;
        removeDuplicateHeading(chapterDiv, data.title);
        contentArea.appendChild(chapterDiv);

        IcecreamReader._continuousRendered.add(chapterIndex);
    } catch (e) {
        console.warn('[Continuous] Failed to append chapter', chapterIndex, e);
    }
}

/**
 * Prepend a chapter to the continuous scroll content
 */
async function prependChapter(chapterIndex) {
    if (!IcecreamReader._continuousRendered) IcecreamReader._continuousRendered = new Set();
    if (IcecreamReader._continuousRendered.has(chapterIndex)) return;

    try {
        const response = await fetch(`/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`);
        if (!response.ok) return;
        const data = await response.json();
        const formattedHtml = formatChapterContent(data.content);

        IcecreamReader.chapterCache.set(chapterIndex, {
            data: data,
            html: formattedHtml,
            timestamp: Date.now()
        });
        if (data.estimated_pages) {
            IcecreamReader.chapterPageCounts[chapterIndex] = data.estimated_pages;
        }

        const contentArea = document.getElementById('ic-chapter-text');
        const readingArea = document.getElementById('ic-reading-area');
        if (!contentArea || !readingArea) return;

        const oldHeight = readingArea.scrollHeight;

        // Add chapter content at the beginning
        const chapterDiv = document.createElement('div');
        chapterDiv.className = 'ic-continuous-chapter';
        chapterDiv.dataset.chapterIndex = chapterIndex;
        chapterDiv.innerHTML = formattedHtml;
        removeDuplicateHeading(chapterDiv, data.title);

        const divider = document.createElement('div');
        divider.className = 'ic-chapter-divider';
        divider.dataset.chapterIndex = chapterIndex;
        divider.innerHTML = `<h3 class="ic-chapter-divider-title">${escapeHtml(data.title || 'Chapter ' + (chapterIndex + 1))}</h3>`;

        contentArea.insertBefore(chapterDiv, contentArea.firstChild);
        contentArea.insertBefore(divider, chapterDiv);

        // Preserve scroll position after prepending
        const newHeight = readingArea.scrollHeight;
        readingArea.scrollTop += (newHeight - oldHeight);

        IcecreamReader._continuousRendered.add(chapterIndex);
    } catch (e) {
        console.warn('[Continuous] Failed to prepend chapter', chapterIndex, e);
    }
}

/* ========================================
   MENU TOGGLES
   ======================================== */

/**
 * Toggle layout menu
 */
function toggleLayoutMenu() {
    const menu = document.getElementById('ic-layout-menu');
    hideOtherMenus('ic-layout-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Toggle font size menu
 */
function toggleFontSizeMenu() {
    const menu = document.getElementById('ic-font-size-menu');
    hideOtherMenus('ic-font-size-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';

        const slider = document.getElementById('ic-font-size-slider');
        if (slider) {
            slider.value = IcecreamReader.fontSize;
        }
    }
}

/**
 * Toggle zoom menu
 */
function toggleZoomMenu() {
    const menu = document.getElementById('ic-zoom-menu');
    hideOtherMenus('ic-zoom-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';

        const slider = document.getElementById('ic-zoom-slider');
        if (slider) {
            slider.value = IcecreamReader.zoomLevel;
        }
    }
}

/**
 * Toggle speed menu
 */
function toggleSpeedMenu() {
    const menu = document.getElementById('ic-speed-menu');
    hideOtherMenus('ic-speed-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Toggle settings menu
 */
function toggleSettings() {
    toggleSettingsPanel();
}

/**
 * Hide other menus
 */
function hideOtherMenus(exceptId) {
    const menus = ['ic-layout-menu', 'ic-font-size-menu', 'ic-zoom-menu', 'ic-speed-menu', 'ic-settings-menu'];
    menus.forEach(id => {
        if (id !== exceptId) {
            const menu = document.getElementById(id);
            if (menu) menu.style.display = 'none';
        }
    });
}

/* ========================================
   UTILITY FUNCTIONS
   ======================================== */

/**
 * Debounced sync of reader settings to the backend API.
 */
let _syncTimeout = null;
let _initializing = true;
function syncSettingsToServer() {
    if (_initializing) return;  // Skip sync during init — values already on server
    clearTimeout(_syncTimeout);
    _syncTimeout = setTimeout(async () => {
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    theme: IcecreamReader.theme,
                    font_size: parseInt(localStorage.getItem('reader-font-size')) || 16,
                    font_family: localStorage.getItem('reader-font-family') || 'georgia',
                    line_height: (localStorage.getItem('reader-line-height') || '1.8').toString(),
                    page_layout: localStorage.getItem('reader-page-layout') || 'single',
                    tts_speed: (localStorage.getItem('tts-speed') || '1.0').toString(),
                    tts_pitch: parseFloat(localStorage.getItem('tts-pitch') || '1.0'),
                })
            });
        } catch (e) {
            console.warn('Settings sync failed:', e);
        }
    }, 2000);
}

/**
 * Initialize saved preferences — loads from server first, then localStorage as fallback.
 */
function initReaderPreferences() {
    // Server is the source of truth — always load from API first
    fetch('/api/settings')
        .then(r => r.ok ? r.json() : null)
        .then(server => {
            if (server) {
                // Server values always win — write to localStorage so applyPreferences picks them up
                if (server.theme) localStorage.setItem('reader-theme', server.theme);
                if (server.font_size) localStorage.setItem('reader-font-size', String(server.font_size));
                if (server.font_family) localStorage.setItem('reader-font-family', server.font_family);
                if (server.line_height) localStorage.setItem('reader-line-height', server.line_height);
                if (server.page_layout) localStorage.setItem('reader-page-layout', server.page_layout);
                if (server.tts_speed) localStorage.setItem('tts-speed', server.tts_speed);
                if (server.tts_pitch) localStorage.setItem('tts-pitch', String(server.tts_pitch));
            }
            applyPreferences();
        })
        .catch(() => applyPreferences());
}

function applyPreferences() {
    const savedLayout = localStorage.getItem('reader-page-layout') || 'single';
    setPageLayout(savedLayout);

    const savedFontSize = parseInt(localStorage.getItem('reader-font-size')) || 16;
    IcecreamReader.fontSize = savedFontSize;
    setFontSize(savedFontSize);

    const savedZoom = parseInt(localStorage.getItem('reader-zoom')) || 100;
    setZoom(savedZoom);

    const savedSpeed = parseFloat(localStorage.getItem('tts-speed')) || 1.0;
    setSpeed(savedSpeed);

    // Load saved font family
    const savedFontFamily = localStorage.getItem('reader-font-family');
    if (savedFontFamily) {
        const fontSelect = document.getElementById('ic-font-select');
        if (fontSelect) {
            fontSelect.value = savedFontFamily;
        }
        setFontFamily(savedFontFamily);
    }

    // Load saved line height
    const savedLineHeight = parseFloat(localStorage.getItem('reader-line-height'));
    if (savedLineHeight) {
        IcecreamReader.lineHeight = savedLineHeight;
        document.querySelectorAll('.ic-chapter-text').forEach(el => {
            el.style.setProperty('line-height', savedLineHeight.toString(), 'important');
        });
        const lsSlider = document.getElementById('ic-line-spacing-slider-sidebar');
        if (lsSlider) lsSlider.value = Math.round(savedLineHeight * 10);
        const lsDisplay = document.getElementById('ic-line-spacing-value');
        if (lsDisplay) lsDisplay.textContent = savedLineHeight.toFixed(1);
    }

    // Load saved volume
    const savedVolume = parseInt(localStorage.getItem('reader-volume'));
    if (savedVolume) {
        IcecreamReader.volume = savedVolume;
        const inlineSlider = document.getElementById('ic-volume-slider');
        const sidebarSlider = document.getElementById('ic-volume-slider-sidebar');
        if (inlineSlider) inlineSlider.value = savedVolume;
        if (sidebarSlider) sidebarSlider.value = savedVolume;
    }

    // Initialization complete — enable settings sync
    _initializing = false;
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
 * Update scroll progress bar within chapter
 */
function updateScrollProgress() {
    const readingArea = document.getElementById('ic-reading-area');
    const progressBar = document.getElementById('ic-scroll-progress-bar');
    if (!readingArea || !progressBar) return;

    const scrollTop = readingArea.scrollTop;
    const scrollHeight = readingArea.scrollHeight - readingArea.clientHeight;
    if (scrollHeight <= 0) {
        progressBar.style.width = '0%';
        return;
    }
    const progress = (scrollTop / scrollHeight) * 100;
    progressBar.style.width = progress + '%';
}

/**
 * Update progress slider tooltip with chapter name
 */
function updateProgressTooltip(slider, tooltip) {
    const progress = parseFloat(slider.value);
    const targetChapter = Math.min(
        Math.floor((progress / 100) * IcecreamReader.totalChapters),
        IcecreamReader.totalChapters - 1
    );
    const chapterName = IcecreamReader.chapters[targetChapter]
        ? (IcecreamReader.chapters[targetChapter].title || `Chapter ${targetChapter + 1}`)
        : `Chapter ${targetChapter + 1}`;
    tooltip.textContent = chapterName;

    // Position tooltip near thumb
    const sliderRect = slider.getBoundingClientRect();
    const thumbPosition = (progress / 100) * sliderRect.width;
    tooltip.style.left = thumbPosition + 'px';
}

/**
 * Toggle keyboard shortcuts help modal
 */
function toggleHelpModal() {
    const overlay = document.getElementById('ic-help-overlay');
    if (!overlay) return;
    const isVisible = overlay.style.display !== 'none';
    overlay.style.display = isVisible ? 'none' : 'flex';
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

/**
 * Update zoom display
 */
function updateZoomDisplay() {
    const display = document.getElementById('ic-zoom-display');
    if (display) {
        display.textContent = IcecreamReader.zoomLevel + '%';
    }
}

/* ========================================
   NAVIGATION FUNCTIONS
   ======================================== */

/**
 * Go to library
 */
function goToLibrary() {
    window.location.href = '/';
}

/**
 * Toggle fullscreen
 */
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

/**
 * Print current chapter
 */
function printChapter() {
    const title = document.getElementById('ic-chapter-title')?.textContent
        || document.getElementById('ic-book-title')?.textContent || 'Chapter';
    let htmlContent = '';

    // In continuous mode, extract only the current chapter's content
    if (IcecreamReader.pageLayout === 'continuous') {
        const contentArea = document.getElementById('ic-chapter-text');
        const dividers = contentArea ? contentArea.querySelectorAll('.ic-chapter-divider') : [];
        let startEl = null;
        let endEl = null;
        dividers.forEach(d => {
            const idx = parseInt(d.dataset.chapterIndex);
            if (idx === IcecreamReader.currentChapter) startEl = d;
            if (idx === IcecreamReader.currentChapter + 1) endEl = d;
        });
        if (startEl) {
            const fragment = document.createElement('div');
            let node = startEl.nextSibling;
            while (node && node !== endEl) {
                fragment.appendChild(node.cloneNode(true));
                node = node.nextSibling;
            }
            htmlContent = fragment.innerHTML;
        }
    }

    // Fallback: print entire content area (single/double page mode)
    if (!htmlContent) {
        const content = document.getElementById('ic-chapter-text');
        if (!content) return;
        htmlContent = content.innerHTML;
    }

    // Create a hidden iframe for printing (avoids popup blocker)
    let iframe = document.getElementById('ic-print-frame');
    if (!iframe) {
        iframe = document.createElement('iframe');
        iframe.id = 'ic-print-frame';
        iframe.style.cssText = 'position:fixed;left:-9999px;width:0;height:0;border:none;';
        document.body.appendChild(iframe);
    }

    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    doc.write(`<!DOCTYPE html><html><head><title>${escapeHtml(title)}</title>
<style>
  @page { margin: 2cm; }
  body { font-family: Georgia, serif; font-size: 11pt; line-height: 1.7; color: #1a1a1a; max-width: 100%; }
  h1 { font-size: 16pt; margin: 0 0 12pt; }
  h2, h3 { margin: 1em 0 0.4em; }
  p { margin: 0 0 0.6em; text-align: justify; }
  img { max-width: 100%; height: auto; }
  .pdf-space { height: 0.6em; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; font-size: 10pt; }
  th { background: #f0f0f0; font-weight: 600; }
</style></head><body><h1>${escapeHtml(title)}</h1>${htmlContent}</body></html>`);
    doc.close();

    iframe.contentWindow.focus();
    iframe.contentWindow.print();
}

/**
 * Show book info
 */
function showBookInfo() {
    toggleBookInfoPanel();
}

/**
 * Toggle volume
 */
function toggleVolume() {
    toggleVolumeControl();
}

/**
 * Show help
 */
function showHelp() {
    toggleHelpModal();
}

/**
 * Print book
 */
function printBook() {
    window.print();
}

/* ========================================
   ANNOTATION TOOLS (API-backed)
   ======================================== */

let currentSelectionRange = null;

/**
 * Handle text selection
 */
function handleTextSelection() {
    const selection = window.getSelection();
    const text = selection.toString().trim();
    const menu = document.getElementById('ic-selection-menu');

    if (text && text.length > 2) {
        currentSelectionRange = selection.getRangeAt(0).cloneRange();

        const rect = currentSelectionRange.getBoundingClientRect();
        menu.style.display = 'flex';

        // Position centered above selection
        let left = rect.left + (rect.width / 2) - (menu.offsetWidth / 2);
        let top = rect.top - menu.offsetHeight - 10;

        // If above selection is clipped, place below
        if (top < 80) {
            top = rect.bottom + 10;
        }

        // Viewport boundary checks
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        if (left < 10) left = 10;
        if (left + menu.offsetWidth > viewportWidth - 10) {
            left = viewportWidth - menu.offsetWidth - 10;
        }
        if (top + menu.offsetHeight > viewportHeight - 10) {
            top = rect.top - menu.offsetHeight - 10;
        }

        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
    } else {
        if (menu) menu.style.display = 'none';
        currentSelectionRange = null;
    }
}

/**
 * Get character offset of selection start within chapter content div
 */
function getSelectionOffsets() {
    const contentArea = document.getElementById('ic-chapter-text');
    if (!contentArea || !currentSelectionRange) return { start: 0, end: 0 };

    const preRange = document.createRange();
    preRange.selectNodeContents(contentArea);
    preRange.setEnd(currentSelectionRange.startContainer, currentSelectionRange.startOffset);
    const start = preRange.toString().length;

    const endRange = document.createRange();
    endRange.selectNodeContents(contentArea);
    endRange.setEnd(currentSelectionRange.endContainer, currentSelectionRange.endOffset);
    const end = endRange.toString().length;

    return { start, end };
}

/**
 * Apply highlight and save to API
 */
async function applyHighlight(color) {
    if (!currentSelectionRange) return;

    const selectedText = currentSelectionRange.toString().trim();
    const offsets = getSelectionOffsets();

    const span = document.createElement('span');
    span.className = `ic-highlight hl-${color}`;

    try {
        currentSelectionRange.surroundContents(span);
    } catch (e) {
        console.warn('Cross-node highlighting not fully supported');
    }

    window.getSelection().removeAllRanges();
    document.getElementById('ic-selection-menu').style.display = 'none';

    // Save annotation to API
    try {
        await fetch(`/api/books/${IcecreamReader.bookId}/annotations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chapter_index: IcecreamReader.currentChapter,
                start_position: offsets.start,
                end_position: offsets.end,
                text: selectedText,
                color: color
            })
        });
    } catch (e) {
        console.error('Failed to save annotation:', e);
    }

    renderNotes();
}

/**
 * Add note to selection and save to API
 */
async function addSelectionNote() {
    if (!currentSelectionRange) return;

    const noteText = prompt("Enter your note:");
    if (!noteText) return;

    const selectedText = currentSelectionRange.toString().trim();
    const offsets = getSelectionOffsets();

    // Apply visual highlight
    const span = document.createElement('span');
    span.className = 'ic-highlight hl-yellow';
    try {
        currentSelectionRange.surroundContents(span);
    } catch (e) {
        console.warn('Cross-node highlighting not fully supported');
    }

    window.getSelection().removeAllRanges();
    document.getElementById('ic-selection-menu').style.display = 'none';

    // Save annotation with note to API
    try {
        await fetch(`/api/books/${IcecreamReader.bookId}/annotations`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chapter_index: IcecreamReader.currentChapter,
                start_position: offsets.start,
                end_position: offsets.end,
                text: selectedText,
                color: 'yellow',
                note: noteText
            })
        });

        // Also save as a note
        await fetch(`/api/books/${IcecreamReader.bookId}/notes`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chapter_index: IcecreamReader.currentChapter,
                position_in_chapter: offsets.start,
                content: noteText,
                color: 'yellow',
                quoted_text: selectedText
            })
        });
    } catch (e) {
        console.error('Failed to save note:', e);
    }

    renderNotes();
    showNotesPanel();
}

/**
 * Copy selection
 */
function copySelection() {
    const text = window.getSelection().toString();
    if (text) {
        navigator.clipboard.writeText(text).then(() => {
            showToast('Copied to clipboard');
            document.getElementById('ic-selection-menu').style.display = 'none';
        });
    }
}

/**
 * Load annotations from API for current chapter and re-apply highlights
 */
async function loadAnnotations() {
    renderNotes();

    try {
        const response = await fetch(
            `/api/books/${IcecreamReader.bookId}/annotations?chapter_index=${IcecreamReader.currentChapter}`
        );
        if (!response.ok) return;
        const data = await response.json();
        const annotations = data.annotations || [];

        if (annotations.length === 0) return;

        const contentArea = document.getElementById('ic-chapter-text');
        if (!contentArea) return;

        // Re-apply highlights by searching for annotation text in content
        annotations.forEach(anno => {
            const text = anno.text;
            if (!text || text.length < 3) return;

            const walker = document.createTreeWalker(
                contentArea,
                NodeFilter.SHOW_TEXT,
                null
            );

            const textNodes = [];
            while (walker.nextNode()) textNodes.push(walker.currentNode);

            for (const node of textNodes) {
                const idx = node.textContent.indexOf(text);
                if (idx === -1) continue;

                try {
                    const range = document.createRange();
                    range.setStart(node, idx);
                    range.setEnd(node, idx + text.length);

                    const span = document.createElement('span');
                    span.className = `ic-highlight hl-${anno.color}`;
                    span.dataset.annotationId = anno.id;
                    range.surroundContents(span);
                } catch (e) {
                    // Skip cross-node matches
                }
                break;
            }
        });
    } catch (e) {
        console.error('Failed to load annotations:', e);
    }
}

/**
 * Render notes panel — combines notes and annotations from API
 */
async function renderNotes() {
    const list = document.getElementById('ic-notes-list');
    if (!list) return;

    try {
        const [notesRes, annotationsRes] = await Promise.all([
            fetch(`/api/books/${IcecreamReader.bookId}/notes`),
            fetch(`/api/books/${IcecreamReader.bookId}/annotations`)
        ]);

        const notesData = notesRes.ok ? await notesRes.json() : { notes: [] };
        const annosData = annotationsRes.ok ? await annotationsRes.json() : { annotations: [] };

        const notes = (notesData.notes || []).map(n => ({ ...n, _type: 'note' }));
        const annotations = (annosData.annotations || []).map(a => ({ ...a, _type: 'annotation' }));

        const allItems = [...notes, ...annotations].sort(
            (a, b) => new Date(b.created_at) - new Date(a.created_at)
        );

        if (allItems.length === 0) {
            list.innerHTML = `
                <div class="ic-sidebar-empty">
                    <div class="ic-sidebar-empty-icon">${EmptyStateIcons.note}</div>
                    <div class="ic-sidebar-empty-text">No notes or highlights yet</div>
                    <div class="ic-sidebar-empty-hint">Select text in the reader to add notes</div>
                </div>`;
            return;
        }

        list.innerHTML = allItems.map(item => {
            if (item._type === 'note') {
                return `
                    <div class="ic-note-item" style="border-left-color: var(--ic-highlight-${item.color || 'yellow'})">
                        <div class="ic-note-header">
                            <span class="ic-note-badge">Note</span>
                            <button class="ic-note-delete" onclick="deleteNote(${item.id})" title="Delete">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                                </svg>
                            </button>
                        </div>
                        ${item.quoted_text ? `<div class="ic-note-quote">${escapeHtml(item.quoted_text)}</div>` : ''}
                        <div class="ic-note-comment">${escapeHtml(item.content)}</div>
                        <div class="ic-note-meta">
                            Chapter ${item.chapter_index + 1} &bull; ${new Date(item.created_at).toLocaleDateString()}
                        </div>
                    </div>
                `;
            } else {
                return `
                    <div class="ic-note-item" style="border-left-color: var(--ic-highlight-${item.color || 'yellow'})">
                        <div class="ic-note-header">
                            <span class="ic-note-badge">Highlight</span>
                            <button class="ic-note-delete" onclick="deleteAnnotation(${item.id})" title="Delete">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                                </svg>
                            </button>
                        </div>
                        <div class="ic-note-text">${escapeHtml(item.text)}</div>
                        ${item.note ? `<div class="ic-note-comment">${escapeHtml(item.note)}</div>` : ''}
                        <div class="ic-note-meta">
                            Chapter ${item.chapter_index + 1} &bull; ${new Date(item.created_at).toLocaleDateString()}
                        </div>
                    </div>
                `;
            }
        }).join('');
    } catch (e) {
        console.error('Failed to render notes:', e);
        list.innerHTML = '<div class="ic-sidebar-empty">Failed to load notes.</div>';
    }
}

/**
 * Delete annotation via API
 */
async function deleteAnnotation(annotationId) {
    try {
        await fetch(`/api/annotations/${annotationId}`, { method: 'DELETE' });
        showToast('Highlight removed');
        loadAnnotations();
    } catch (e) {
        console.error('Failed to delete annotation:', e);
    }
}

/**
 * Delete note via API
 */
async function deleteNote(noteId) {
    try {
        await fetch(`/api/notes/${noteId}`, { method: 'DELETE' });
        showToast('Note deleted');
        renderNotes();
    } catch (e) {
        console.error('Failed to delete note:', e);
    }
}

/* ========================================
   BOOKMARKS (API-backed)
   ======================================== */

/**
 * Add bookmark via API
 */
async function addBookmark() {
    const chapterName = document.getElementById('ic-chapter-title').textContent || `Chapter ${IcecreamReader.currentChapter + 1}`;

    try {
        const response = await fetch(`/api/books/${IcecreamReader.bookId}/bookmarks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chapter_index: IcecreamReader.currentChapter,
                position_in_chapter: 0,
                title: chapterName
            })
        });

        if (response.status === 409) {
            showToast('Already bookmarked');
            return;
        }

        if (!response.ok) throw new Error('Failed to add bookmark');

        showToast('Bookmark added');
        renderBookmarks();
    } catch (e) {
        console.error('Failed to add bookmark:', e);
        showToast('Failed to add bookmark');
    }
}

/**
 * Render bookmarks from API
 */
async function renderBookmarks() {
    const list = document.getElementById('ic-bookmarks-list');
    if (!list) return;

    try {
        const response = await fetch(`/api/books/${IcecreamReader.bookId}/bookmarks`);
        if (!response.ok) throw new Error('Failed to load bookmarks');
        const data = await response.json();
        const bookmarks = data.bookmarks || [];

        if (bookmarks.length === 0) {
            list.innerHTML = `
                <div class="ic-sidebar-empty">
                    <div class="ic-sidebar-empty-icon">${EmptyStateIcons.bookmark}</div>
                    <div class="ic-sidebar-empty-text">No bookmarks yet</div>
                    <div class="ic-sidebar-empty-hint">Click "Add bookmark" to save your place</div>
                </div>`;
            return;
        }

        list.innerHTML = bookmarks.reverse().map(b => `
            <div class="ic-bookmark-item">
                <div class="ic-bookmark-content" onclick="loadChapter(${b.chapter_index})">
                    <div style="font-size: 13px; font-weight: 500;">${escapeHtml(b.title || 'Chapter ' + (b.chapter_index + 1))}</div>
                    <div style="font-size: 11px; color: #999;">${new Date(b.created_at).toLocaleDateString()}</div>
                </div>
                <button class="ic-bookmark-delete" onclick="deleteBookmark(${b.id})" title="Delete">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                    </svg>
                </button>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to render bookmarks:', e);
        list.innerHTML = '<div class="ic-sidebar-empty">Failed to load bookmarks.</div>';
    }
}

/**
 * Delete bookmark via API
 */
async function deleteBookmark(bookmarkId) {
    try {
        await fetch(`/api/bookmarks/${bookmarkId}`, { method: 'DELETE' });
        showToast('Bookmark removed');
        renderBookmarks();
    } catch (e) {
        console.error('Failed to delete bookmark:', e);
    }
}

/* ========================================
   AI SUMMARIZATION (Chapter + Book)
   ======================================== */

/**
 * Generate chapter summary
 */
async function generateSummary() {
    const summaryContainer = document.getElementById('ic-summary-content');
    const genBtn = document.getElementById('ic-generate-btn');

    // Ensure chapter tab is active
    document.getElementById('ic-summary-tab-chapter')?.classList.add('active');
    document.getElementById('ic-summary-tab-book')?.classList.remove('active');

    // Disable button, show loading
    if (genBtn) { genBtn.disabled = true; genBtn.classList.add('loading'); }

    summaryContainer.innerHTML = `
        <div class="ic-loading" style="text-align: center; padding: 40px 20px;">
            <div class="ic-spinner"></div>
            <p style="margin-top: 12px;">Generating summary...</p>
            <p style="font-size: 12px; color: #999; margin-top: 8px;">This may take a moment.</p>
        </div>
    `;
    showSummaryActions(false);

    try {
        const response = await fetch(
            `/api/books/${IcecreamReader.bookId}/summary/${IcecreamReader.currentChapter}?refresh=true`
        );
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.message || 'Failed to generate summary');
        }
        const data = await response.json();

        summaryContainer.innerHTML = `
            <div class="ic-summary-text">
                <p class="ic-summary-meta">Generated using ${data.provider || 'AI'}</p>
                ${formatSummaryText(data.summary)}
            </div>
        `;
        showSummaryActions(true);

    } catch (error) {
        console.error('Failed to generate summary:', error);
        summaryContainer.innerHTML = `
            <div class="ic-summary-empty" role="alert" aria-live="polite">
                <p class="ic-summary-empty-text" style="color: #d32f2f;">
                    ${escapeHtml(error.message || 'Failed to generate summary.')}
                </p>
            </div>
        `;
    } finally {
        if (genBtn) { genBtn.disabled = false; genBtn.classList.remove('loading'); }
    }
}

/**
 * Generate full book summary
 */
async function generateBookSummary() {
    const summaryContainer = document.getElementById('ic-summary-content');
    const genBtn = document.getElementById('ic-generate-btn');

    // Ensure book tab is active
    document.getElementById('ic-summary-tab-book')?.classList.add('active');
    document.getElementById('ic-summary-tab-chapter')?.classList.remove('active');

    // Disable button, show loading
    if (genBtn) { genBtn.disabled = true; genBtn.classList.add('loading'); }

    summaryContainer.innerHTML = `
        <div class="ic-loading" style="text-align: center; padding: 40px 20px;">
            <div class="ic-spinner"></div>
            <p style="margin-top: 12px;">Generating full book summary...</p>
            <p style="font-size: 12px; color: #999; margin-top: 8px;">This may take a while for large books.</p>
        </div>
    `;
    showSummaryActions(false);

    try {
        const response = await fetch(
            `/api/books/${IcecreamReader.bookId}/summary?refresh=true`
        );
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.message || 'Failed to generate book summary');
        }
        const data = await response.json();

        summaryContainer.innerHTML = `
            <div class="ic-summary-text">
                <p class="ic-summary-meta">Full book summary &bull; Generated using ${data.provider || 'AI'}</p>
                ${formatSummaryText(data.summary)}
            </div>
        `;
        showSummaryActions(true);

    } catch (error) {
        console.error('Failed to generate book summary:', error);
        summaryContainer.innerHTML = `
            <div class="ic-summary-empty" role="alert" aria-live="polite">
                <p class="ic-summary-empty-text" style="color: #d32f2f;">
                    ${escapeHtml(error.message || 'Failed to generate book summary.')}
                </p>
            </div>
        `;
    } finally {
        if (genBtn) { genBtn.disabled = false; genBtn.classList.remove('loading'); }
    }
}

/**
 * Format summary text with basic markdown-like rendering
 */
function formatSummaryText(summary) {
    if (!summary) return '<p>No summary available.</p>';

    const lines = summary.split('\n');
    let html = '';
    let inList = false;

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
            if (inList) { html += '</ul>'; inList = false; }
            continue;
        }

        // Bullet points
        if (/^[-•*]\s/.test(trimmed)) {
            if (!inList) { html += '<ul class="ic-summary-list">'; inList = true; }
            html += `<li>${formatInline(trimmed.replace(/^[-•*]\s/, ''))}</li>`;
            continue;
        }

        // Numbered items
        if (/^\d+\.\s/.test(trimmed)) {
            if (!inList) { html += '<ul class="ic-summary-list">'; inList = true; }
            html += `<li>${formatInline(trimmed.replace(/^\d+\.\s/, ''))}</li>`;
            continue;
        }

        if (inList) { html += '</ul>'; inList = false; }

        // Headings (## or all-caps short lines)
        if (/^##\s/.test(trimmed)) {
            html += `<h4 class="ic-summary-heading">${formatInline(trimmed.replace(/^##\s/, ''))}</h4>`;
        } else {
            html += `<p>${formatInline(trimmed)}</p>`;
        }
    }

    if (inList) html += '</ul>';
    return html;
}

/**
 * Format inline text (bold, italic) — alias for formatInlineText.
 */
function formatInline(text) {
    return formatInlineText(text);
}

/**
 * Set summary length preference
 */
function setSummaryLength(length) {
    IcecreamReader.summaryLength = length;
    localStorage.setItem('reader-summary-length', length);
    document.querySelectorAll('.ic-length-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.length === length);
    });
}

/**
 * Toggle auto-summarize on chapter load
 */
function toggleAutoSummary(enabled) {
    IcecreamReader.autoSummary = enabled;
    localStorage.setItem('reader-auto-summary', enabled);
}

/**
 * Check AI provider status and display in summary panel
 */
async function checkAIProvider() {
    const dot = document.querySelector('.ic-summary-provider-dot');
    const text = document.getElementById('ic-summary-provider-text');
    if (!text) return;

    try {
        const resp = await fetch('/api/ai/providers');
        if (!resp.ok) throw new Error('Failed');
        const data = await resp.json();
        const active = data.providers?.find(p => p.available);
        if (active) {
            text.textContent = `${active.name} (${active.model})`;
            dot?.classList.add('available');
        } else {
            text.textContent = 'No AI provider available';
            dot?.classList.add('unavailable');
        }
        // Also render provider cards in settings
        renderAIProviders(data.providers || []);
    } catch {
        text.textContent = 'AI status unknown';
    }
}

/**
 * Render AI provider status cards in the settings panel
 */
function renderAIProviders(providers) {
    const container = document.getElementById('ic-ai-providers-list');
    if (!container) return;

    if (!providers.length) {
        container.innerHTML = '<div class="ic-ai-provider-loading">No providers configured</div>';
        return;
    }

    const displayNames = {
        google: 'Google Gemini',
        groq: 'Groq',
        ollama_cloud: 'Ollama Cloud',
        ollama_local: 'Ollama Local',
    };

    container.innerHTML = providers.map(p => {
        const dotClass = p.is_current ? 'current' : (p.available ? 'online' : 'offline');
        const badge = p.available
            ? (p.is_current ? '<span class="ic-ai-provider-badge">Active</span>' : '<span class="ic-ai-provider-badge">Ready</span>')
            : '<span class="ic-ai-provider-badge inactive">Offline</span>';
        return `
            <div class="ic-ai-provider-card">
                <div class="ic-ai-provider-dot ${dotClass}"></div>
                <div class="ic-ai-provider-info">
                    <div class="ic-ai-provider-name">${displayNames[p.name] || p.name}</div>
                    <div class="ic-ai-provider-model">${escapeHtml(p.model)}</div>
                </div>
                ${badge}
            </div>
        `;
    }).join('');
}

/**
 * Test AI provider connection
 */
async function testAIConnection() {
    const provider = document.getElementById('ic-ai-provider-select')?.value;
    const apiKey = document.getElementById('ic-ai-key-input')?.value?.trim();
    const btn = document.getElementById('ic-ai-test-btn');
    if (!btn || !provider) return;

    // Ollama uses URL, not API key
    if (provider === 'ollama_local') {
        const url = document.getElementById('ic-ollama-url-input')?.value?.trim();
        if (!url) { showToast('Enter Ollama URL'); return; }
        btn.className = 'ic-ai-test-btn testing';
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V2A10 10 0 0 0 2 12h2a8 8 0 0 1 8-8z" opacity="0.3"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></path></svg> Testing';
        try {
            const resp = await fetch(url + '/api/tags', { signal: AbortSignal.timeout(5000) });
            if (resp.ok) {
                btn.className = 'ic-ai-test-btn success';
                btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> OK';
            } else {
                throw new Error('Not reachable');
            }
        } catch (e) {
            btn.className = 'ic-ai-test-btn fail';
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg> Fail';
        }
        setTimeout(() => { btn.className = 'ic-ai-test-btn'; btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> Test'; }, 3000);
        return;
    }

    if (!apiKey) { showToast('Enter API key'); return; }

    btn.className = 'ic-ai-test-btn testing';
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V2A10 10 0 0 0 2 12h2a8 8 0 0 1 8-8z" opacity="0.3"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite"/></path></svg> Testing';

    try {
        const resp = await fetch('/api/settings/test-ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: apiKey }),
        });

        if (resp.ok) {
            btn.className = 'ic-ai-test-btn success';
            btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> OK';
        } else {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail?.message || 'Failed');
        }
    } catch (e) {
        btn.className = 'ic-ai-test-btn fail';
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg> Fail`;
        showToast('Connection failed: ' + e.message);
    }

    setTimeout(() => {
        btn.className = 'ic-ai-test-btn';
        btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> Test';
    }, 3000);
}

/**
 * Save AI API key to server
 */
async function saveAIKey() {
    const provider = document.getElementById('ic-ai-provider-select')?.value;
    const apiKey = document.getElementById('ic-ai-key-input')?.value?.trim();
    if (!provider || !apiKey) { showToast('Enter provider and API key'); return; }

    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ai_provider: provider, ai_api_key: apiKey }),
        });
        showToast(`${provider} key saved. Reloading providers...`);
        document.getElementById('ic-ai-key-input').value = '';
        // Re-check providers after a brief delay
        setTimeout(() => checkAIProvider(), 1000);
    } catch (e) {
        showToast('Failed to save: ' + e.message);
    }
}

/**
 * Save Ollama URL
 */
async function saveOllamaUrl() {
    const url = document.getElementById('ic-ollama-url-input')?.value?.trim();
    if (!url) return;

    try {
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ollama_url: url }),
        });
        showToast('Ollama URL saved');
        setTimeout(() => checkAIProvider(), 1000);
    } catch (e) {
        showToast('Failed to save: ' + e.message);
    }
}

/**
 * Copy current summary to clipboard
 */
function copySummary() {
    const summaryText = document.getElementById('ic-summary-content')?.innerText;
    if (summaryText) {
        navigator.clipboard.writeText(summaryText).then(() => {
            showToast('Summary copied to clipboard');
        }).catch(() => {
            showToast('Failed to copy');
        });
    }
}

/**
 * Show/hide the summary actions bar
 */
function showSummaryActions(show) {
    const actions = document.getElementById('ic-summary-actions');
    if (actions) actions.style.display = show ? 'flex' : 'none';
}

// Export functions for onclick handlers
window.readerApp = {
    init: initReader,
    generateSummary,
    generateBookSummary,
    toggleSummary: toggleSummaryPanel
};

window.setSummaryLength = setSummaryLength;
window.toggleAutoSummary = toggleAutoSummary;
window.copySummary = copySummary;

// Make all functions global
window.goToChapter = goToChapter;
window.toggleTOCPanel = toggleTOCPanel;
window.toggleTOCSection = toggleTOCSection;
window.showNotesPanel = showNotesPanel;
window.closeNotesPanel = closeNotesPanel;
window.showBookmarksPanel = showBookmarksPanel;
window.closeBookmarksPanel = closeBookmarksPanel;
window.showSearchPanel = showSearchPanel;
window.closeSearchPanel = closeSearchPanel;
window.toggleSummaryPanel = toggleSummaryPanel;
window.switchSummaryTab = switchSummaryTab;
window.toggleBookInfoPanel = toggleBookInfoPanel;
window.toggleSettingsPanel = toggleSettingsPanel;
window.toggleVolumeControl = toggleVolumeControl;
window.handleSearch = handleSearch;
window.clearSearch = clearSearch;
window.setTheme = setTheme;
window.setZoom = setZoom;
window.adjustZoom = adjustZoom;
window.setFontSize = setFontSize;
window.setFontFamily = setFontFamily;
window.adjustFontSize = adjustFontSize;
window.adjustLineSpacing = adjustLineSpacing;
window.setLineSpacing = setLineSpacing;
window.setSpeed = setSpeed;
window.setVolume = setVolume;
window.setPageLayout = setPageLayout;
window.toggleLayoutMenu = toggleLayoutMenu;
window.toggleFontSizeMenu = toggleFontSizeMenu;
window.toggleZoomMenu = toggleZoomMenu;
window.toggleSpeedMenu = toggleSpeedMenu;
window.toggleSettings = toggleSettings;
window.toggleSettingsPanel = toggleSettingsPanel;
window.toggleTTS = toggleTTS;
window.toggleVolume = toggleVolume;
window.showBookInfo = showBookInfo;
window.showHelp = showHelp;
window.printBook = printBook;
window.printChapter = printChapter;
window.goToLibrary = goToLibrary;
window.toggleFullscreen = toggleFullscreen;
window.applyHighlight = applyHighlight;
window.addSelectionNote = addSelectionNote;
window.copySelection = copySelection;
window.addBookmark = addBookmark;
window.deleteBookmark = deleteBookmark;
window.deleteAnnotation = deleteAnnotation;
window.testAIConnection = testAIConnection;
window.saveAIKey = saveAIKey;
window.saveOllamaUrl = saveOllamaUrl;

// Toggle AI key input based on provider selection
(function() {
    const select = document.getElementById('ic-ai-provider-select');
    const keySection = document.getElementById('ic-ai-key-section');
    const ollamaSection = document.getElementById('ic-ai-ollama-section');
    if (select) {
        select.addEventListener('change', function() {
            const isOllama = this.value === 'ollama_local';
            if (keySection) keySection.style.display = isOllama ? 'none' : '';
            if (ollamaSection) ollamaSection.style.display = isOllama ? '' : 'none';
            // Update placeholder
            const input = document.getElementById('ic-ai-key-input');
            if (input) input.placeholder = isOllama ? '' : 'Enter API key...';
        });
        // Initial state
        const isOllama = select.value === 'ollama_local';
        if (ollamaSection) ollamaSection.style.display = isOllama ? '' : 'none';
    }
})();
window.deleteNote = deleteNote;
window.toggleHelpModal = toggleHelpModal;
window.updateScrollProgress = updateScrollProgress;

/* ========================================
   KEYBOARD SHORTCUTS
   ======================================== */

document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
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
