// Reader Page JavaScript for eBook Manager
// Pixel-Perfect Icecream UI Clone

(function() {
    'use strict';

    let bookId = null;
    let currentChapter = 0;
    let totalChapters = 1;
    let currentChapterText = "";
    let summaryVisible = false;
    let currentZoom = 100;
    let annotationMode = false;
    let annotations = [];
    let tocData = [];
    let bookmarks = [];
    let notes = [];
    let pendingAnnotation = null;

    /**
     * Initialize the reader app
     * @param {number} id - Book ID
     */
    function init(id) {
        bookId = id;
        loadChapter(0);
        loadBookTitle();
        initializeFromStorage();
        initializeKeyboardNavigation();
        initializeAnnotationMode();
        initializeVoiceSelector();
    }

    /**
     * Initialize settings from localStorage
     */
    function initializeFromStorage() {
        // Restore theme
        const savedTheme = localStorage.getItem('reader-theme') || 'day';
        setTheme(savedTheme);

        // Restore zoom
        const savedZoom = localStorage.getItem('reader-zoom');
        if (savedZoom) {
            currentZoom = parseInt(savedZoom);
            applyZoom();
        }

        // Restore reading speed
        const savedSpeed = localStorage.getItem('reader-speed');
        if (savedSpeed) {
            document.getElementById('speed-selector').value = savedSpeed;
        }
    }

    /**
     * Initialize annotation mode
     */
    function initializeAnnotationMode() {
        const readerContent = document.getElementById('chapter-text');

        // Handle text selection for annotations
        document.addEventListener('mouseup', handleTextSelection);
    }

    /**
     * Handle text selection for annotations
     */
    function handleTextSelection() {
        if (!annotationMode) return;

        const selection = window.getSelection();
        const selectedText = selection.toString().trim();

        if (selectedText.length > 0) {
            const range = selection.getRangeAt(0);
            const chapterTextDiv = document.getElementById('chapter-text');

            // Calculate position in chapter
            const preCaretRange = range.cloneRange();
            preCaretRange.selectNodeContents(chapterTextDiv);
            preCaretRange.setEnd(range.startContainer, range.startOffset);
            const startPosition = preCaretRange.toString().length;

            const endPosition = startPosition + selectedText.length;

            pendingAnnotation = {
                text: selectedText,
                start_position: startPosition,
                end_position: endPosition,
                chapter_index: currentChapter
            };

            // Show note modal
            showNoteModal(selectedText);
        }
    }

    /**
     * Load a chapter
     * @param {number} chapterIndex - Chapter index
     */
    async function loadChapter(chapterIndex) {
        showLoading();

        try {
            const response = await fetch(`/api/books/${bookId}/chapter/${chapterIndex}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            currentChapter = data.current_chapter;
            totalChapters = data.total_chapters;

            // Update content
            const chapterTextDiv = document.getElementById('chapter-text');
            chapterTextDiv.innerHTML = `
                <h1 class="chapter-title">${escapeHtml(data.title)}</h1>
                <div class="chapter-content">
                    ${data.content}
                </div>
            `;

            currentChapterText = data.content;

            // Update UI
            updatePageInfo();
            updateProgressBar();

            // Load and render annotations for this chapter
            await loadAnnotations();

            // Hide summary when changing chapters
            if (summaryVisible) {
                toggleSummary();
            }

            // Stop TTS if playing
            if (window.tts && window.tts.isSpeaking()) {
                window.tts.stop();
            }

        } catch (error) {
            console.error('Failed to load chapter:', error);
            const chapterTextDiv = document.getElementById('chapter-text');
            chapterTextDiv.innerHTML = `
                <div class="error-state">
                    <p class="error-title">Failed to load chapter</p>
                    <p class="error-message">${error.message}</p>
                    <button onclick="window.readerApp.loadChapter(${chapterIndex})" class="retry-button">Retry</button>
                </div>
            `;
        }
    }

    /**
     * Navigate to previous chapter
     */
    function prevChapter() {
        if (currentChapter > 0) {
            loadChapter(currentChapter - 1);
        }
    }

    /**
     * Navigate to next chapter
     */
    function nextChapter() {
        if (currentChapter < totalChapters - 1) {
            loadChapter(currentChapter + 1);
        }
    }

    /**
     * Update progress bar and save progress
     */
    async function updateProgressBar() {
        const progress = totalChapters > 0 ? ((currentChapter + 1) / totalChapters) * 100 : 0;

        const progressBar = document.getElementById('progress-bar');
        if (progressBar) {
            progressBar.style.width = `${progress}%`;
        }

        // Save progress to server
        try {
            await fetch(`/api/books/${bookId}/progress`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chapter_index: currentChapter,
                    progress: progress
                })
            });
        } catch (error) {
            console.error('Failed to save progress:', error);
        }
    }

    /**
     * Update page info display
     */
    function updatePageInfo() {
        const currentChapterDisplay = document.getElementById('current-chapter-display');
        const progressPercent = document.getElementById('progress-percent');

        if (currentChapterDisplay) {
            currentChapterDisplay.textContent = `Chapter ${currentChapter + 1} of ${totalChapters}`;
        }

        if (progressPercent) {
            const progress = totalChapters > 0 ? Math.round(((currentChapter + 1) / totalChapters) * 100) : 0;
            progressPercent.textContent = `${progress}%`;
        }
    }

    /**
     * Show loading state
     */
    function showLoading() {
        const chapterTextDiv = document.getElementById('chapter-text');
        chapterTextDiv.innerHTML = `
            <div class="loading-state">
                <div class="loading-spinner-inline"></div>
                <p>Loading chapter...</p>
            </div>
        `;
    }

    /**
     * Toggle AI Summary sidebar
     */
    function toggleSummary() {
        const sidebar = document.getElementById('summary-sidebar');
        summaryVisible = !sidebar.classList.contains('closed');

        if (summaryVisible) {
            sidebar.classList.add('closed');
            summaryVisible = false;
        } else {
            sidebar.classList.remove('closed');
            summaryVisible = true;
            loadSummary();
        }
    }

    /**
     * Load AI summary for current chapter
     */
    async function loadSummary() {
        const summaryTextDiv = document.getElementById('summary-text');
        summaryTextDiv.innerHTML = '<p class="summary-loading">Generating summary...</p>';

        try {
            const response = await fetch(`/api/books/${bookId}/summary/${currentChapter}?refresh=false`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            summaryTextDiv.innerHTML = `
                <div class="summary-content">
                    ${data.summary}
                </div>
                <p class="summary-meta">
                    Generated by ${data.provider} at ${new Date(data.created_at).toLocaleString()}
                </p>
                <button onclick="window.readerApp.regenerateSummary()" class="summary-regenerate-btn">Regenerate</button>
            `;
        } catch (error) {
            console.error('Failed to load summary:', error);
            summaryTextDiv.innerHTML = `
                <p class="summary-error">Failed to generate summary.</p>
                <p class="summary-meta">${error.message}</p>
                <p class="summary-meta">Make sure you have configured an AI provider in .env</p>
                <button onclick="window.readerApp.generateSummary()" class="summary-regenerate-btn">Try Again</button>
            `;
        }
    }

    /**
     * Generate AI summary for current chapter
     */
    async function generateSummary() {
        const summaryTextDiv = document.getElementById('summary-text');
        summaryTextDiv.innerHTML = '<p class="summary-loading">Generating summary...</p>';

        try {
            const response = await fetch(`/api/books/${bookId}/summary/${currentChapter}?refresh=true`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            summaryTextDiv.innerHTML = `
                <div class="summary-content">
                    ${data.summary}
                </div>
                <p class="summary-meta">
                    Generated by ${data.provider} at ${new Date(data.created_at).toLocaleString()}
                </p>
                <button onclick="window.readerApp.regenerateSummary()" class="summary-regenerate-btn">Regenerate</button>
            `;
        } catch (error) {
            console.error('Failed to generate summary:', error);
            summaryTextDiv.innerHTML = `
                <p class="summary-error">Failed to generate summary.</p>
                <p class="summary-meta">${error.message}</p>
                <p class="summary-meta">Make sure you have configured an AI provider in .env</p>
                <button onclick="window.readerApp.generateSummary()" class="summary-regenerate-btn">Try Again</button>
            `;
        }
    }

    /**
     * Regenerate summary
     */
    async function regenerateSummary() {
        try {
            const response = await fetch(`/api/books/${bookId}/summary/${currentChapter}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ regenerate: true })
            });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            const summaryTextDiv = document.getElementById('summary-text');
            summaryTextDiv.innerHTML = `
                <div class="summary-content">
                    ${data.summary}
                </div>
                <p class="summary-meta">
                    Generated by ${data.provider} at ${new Date(data.created_at).toLocaleString()}
                </p>
                <button onclick="window.readerApp.regenerateSummary()" class="summary-regenerate-btn">Regenerate</button>
            `;
        } catch (error) {
            console.error('Failed to regenerate summary:', error);
            alert('Failed to regenerate summary: ' + error.message);
        }
    }

    /**
     * Load book title
     */
    async function loadBookTitle() {
        try {
            const response = await fetch(`/api/books/${bookId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            document.title = `${data.title} - eBook Manager`;
        } catch (error) {
            console.error('Failed to load book title:', error);
            document.title = 'Reader - eBook Manager';
        }
    }

    /**
     * Initialize keyboard navigation
     */
    function initializeKeyboardNavigation() {
        document.addEventListener('keydown', (e) => {
            // Don't trigger if typing in input fields
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
                return;
            }

            switch (e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    prevChapter();
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    nextChapter();
                    break;
                case 'Escape':
                    if (summaryVisible) {
                        toggleSummary();
                    }
                    if (annotationMode) {
                        toggleAnnotationMode();
                    }
                    // Close shortcuts modal if open
                    const shortcutsModal = document.getElementById('shortcuts-modal');
                    if (shortcutsModal && shortcutsModal.classList.contains('show')) {
                        toggleShortcutsModal();
                    }
                    break;
                case 'f':
                case 'F':
                    e.preventDefault();
                    toggleFullscreen();
                    break;
                case 's':
                case 'S':
                    e.preventDefault();
                    toggleSummary();
                    break;
                case 't':
                case 'T':
                    e.preventDefault();
                    if (window.tts && window.tts.toggle) {
                        window.tts.toggle();
                    }
                    break;
                case '+':
                case '=':
                    e.preventDefault();
                    zoomIn();
                    break;
                case '-':
                case '_':
                    e.preventDefault();
                    zoomOut();
                    break;
                case 'c':
                case 'C':
                    e.preventDefault();
                    toggleContents();
                    break;
                case 'b':
                case 'B':
                    e.preventDefault();
                    if (e.ctrlKey || e.metaKey) {
                        toggleAnnotationMode();
                    } else {
                        toggleBookmarks();
                    }
                    break;
                case 'n':
                case 'N':
                    e.preventDefault();
                    toggleNotes();
                    break;
                case '?':
                    if (e.ctrlKey || e.metaKey) {
                        e.preventDefault();
                        toggleShortcutsModal();
                    }
                    break;
                case 'd':
                case 'D':
                    e.preventDefault();
                    setTheme('day');
                    break;
                case 'Alt':
                    // Handled separately for keyup
                    break;
            }

            // Handle Alt+Left for back to library
            if (e.altKey && e.key === 'ArrowLeft') {
                e.preventDefault();
                goToLibrary();
            }
        });
    }

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ============================================
    // TABLE OF CONTENTS FUNCTIONS
    // ============================================

    /**
     * Load table of contents
     */
    async function loadTOC() {
        const tocContent = document.getElementById('toc-content');
        tocContent.innerHTML = '<div class="sidebar-loading">Loading...</div>';

        try {
            const response = await fetch(`/api/books/${bookId}/toc`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            tocData = data.items;

            renderTOC(tocData);
        } catch (error) {
            console.error('Failed to load TOC:', error);
            tocContent.innerHTML = `<div class="sidebar-error">Failed to load table of contents</div>`;
        }
    }

    /**
     * Render table of contents
     */
    function renderTOC(items) {
        const tocContent = document.getElementById('toc-content');

        if (!items || items.length === 0) {
            tocContent.innerHTML = '<div class="sidebar-empty">No chapters available</div>';
            return;
        }

        let html = '<div class="toc-list">';

        items.forEach(item => {
            const isCurrent = item.index === currentChapter;
            const padding = (item.level - 1) * 16;

            html += `
                <div class="toc-item ${isCurrent ? 'current' : ''}"
                     style="padding-left: ${padding + 12}px"
                     onclick="navigateToChapter(${item.index})">
                    ${escapeHtml(item.title)}
                </div>
            `;
        });

        html += '</div>';
        tocContent.innerHTML = html;
    }

    /**
     * Navigate to specific chapter from TOC
     */
    function navigateToChapter(chapterIndex) {
        loadChapter(chapterIndex);
        // Close TOC sidebar after navigation
        const tocSidebar = document.getElementById('contents-sidebar');
        if (!tocSidebar.classList.contains('closed')) {
            toggleContents();
        }
    }

    // ============================================
    // BOOKMARK FUNCTIONS
    // ============================================

    /**
     * Load bookmarks
     */
    async function loadBookmarks() {
        const bookmarksContent = document.getElementById('bookmarks-content');
        bookmarksContent.innerHTML = '<div class="sidebar-loading">Loading...</div>';

        try {
            const response = await fetch(`/api/books/${bookId}/bookmarks`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            bookmarks = data.bookmarks;

            renderBookmarks();
        } catch (error) {
            console.error('Failed to load bookmarks:', error);
            bookmarksContent.innerHTML = `<div class="sidebar-error">Failed to load bookmarks</div>`;
        }
    }

    /**
     * Render bookmarks
     */
    function renderBookmarks() {
        const bookmarksContent = document.getElementById('bookmarks-content');

        if (!bookmarks || bookmarks.length === 0) {
            bookmarksContent.innerHTML = '<div class="sidebar-empty">No bookmarks yet</div>';
            return;
        }

        let html = '<div class="bookmarks-list">';

        bookmarks.forEach(bookmark => {
            const date = new Date(bookmark.created_at).toLocaleDateString();
            const title = bookmark.title || `Chapter ${bookmark.chapter_index + 1}`;

            html += `
                <div class="bookmark-item">
                    <div class="bookmark-header">
                        <h4 class="bookmark-title">${escapeHtml(title)}</h4>
                        <button class="bookmark-delete" onclick="deleteBookmark(${bookmark.id})" title="Delete">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                            </svg>
                        </button>
                    </div>
                    <p class="bookmark-meta">Chapter ${bookmark.chapter_index + 1} • ${date}</p>
                    ${bookmark.notes ? `<p class="bookmark-notes">${escapeHtml(bookmark.notes)}</p>` : ''}
                    <button class="bookmark-jump-btn" onclick="navigateToBookmark(${bookmark.id})">
                        Go to Bookmark
                    </button>
                </div>
            `;
        });

        html += '</div>';
        bookmarksContent.innerHTML = html;
    }

    /**
     * Add current position as bookmark
     */
    async function addBookmark() {
        const title = prompt('Enter bookmark title (optional):');

        try {
            const response = await fetch(`/api/books/${bookId}/bookmarks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chapter_index: currentChapter,
                    position_in_chapter: 0,
                    title: title || null
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Reload bookmarks
            if (!document.getElementById('bookmarks-sidebar').classList.contains('closed')) {
                await loadBookmarks();
            }

            alert('Bookmark added!');
        } catch (error) {
            console.error('Failed to add bookmark:', error);
            alert('Failed to add bookmark: ' + error.message);
        }
    }

    /**
     * Navigate to bookmark
     */
    async function navigateToBookmark(bookmarkId) {
        try {
            const response = await fetch(`/api/bookmarks/${bookmarkId}/jump`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();

            await loadChapter(data.chapter_index);
            toggleBookmarks();
        } catch (error) {
            console.error('Failed to navigate to bookmark:', error);
            alert('Failed to navigate to bookmark');
        }
    }

    /**
     * Delete bookmark
     */
    async function deleteBookmark(bookmarkId) {
        if (!confirm('Delete this bookmark?')) return;

        try {
            const response = await fetch(`/api/bookmarks/${bookmarkId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            await loadBookmarks();
        } catch (error) {
            console.error('Failed to delete bookmark:', error);
            alert('Failed to delete bookmark');
        }
    }

    // ============================================
    // NOTE FUNCTIONS
    // ============================================

    /**
     * Load notes
     */
    async function loadNotes() {
        const notesContent = document.getElementById('notes-content');
        notesContent.innerHTML = '<div class="sidebar-loading">Loading...</div>';

        try {
            const response = await fetch(`/api/books/${bookId}/notes`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            notes = data.notes;

            renderNotes();
        } catch (error) {
            console.error('Failed to load notes:', error);
            notesContent.innerHTML = `<div class="sidebar-error">Failed to load notes</div>`;
        }
    }

    /**
     * Render notes
     */
    function renderNotes() {
        const notesContent = document.getElementById('notes-content');

        if (!notes || notes.length === 0) {
            notesContent.innerHTML = '<div class="sidebar-empty">No notes yet. Select text and click the annotation button to add notes.</div>';
            return;
        }

        let html = '<div class="notes-list">';

        notes.forEach(note => {
            const date = new Date(note.created_at).toLocaleDateString();
            const colorClass = `note-${note.color}`;

            html += `
                <div class="note-item ${colorClass}">
                    <div class="note-header">
                        <span class="note-chapter">Chapter ${note.chapter_index + 1}</span>
                        <button class="note-delete" onclick="deleteNote(${note.id})" title="Delete">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                            </svg>
                        </button>
                    </div>
                    ${note.quoted_text ? `<p class="note-quoted">"${escapeHtml(note.quoted_text.substring(0, 100))}${note.quoted_text.length > 100 ? '...' : ''}"</p>` : ''}
                    <p class="note-content">${escapeHtml(note.content)}</p>
                    <p class="note-meta">${date}</p>
                    <button class="note-jump-btn" onclick="navigateToNote(${note.id})">
                        Go to Location
                    </button>
                </div>
            `;
        });

        html += '</div>';
        notesContent.innerHTML = html;
    }

    /**
     * Show note modal for creating new note
     */
    function showNoteModal(quotedText = '') {
        const modal = document.getElementById('note-modal');
        const quotedTextDiv = document.getElementById('note-quoted-text');
        const contentTextarea = document.getElementById('note-content');

        if (quotedText) {
            quotedTextDiv.textContent = quotedText.substring(0, 200) + (quotedText.length > 200 ? '...' : '');
            quotedTextDiv.style.display = 'block';
        } else {
            quotedTextDiv.style.display = 'none';
        }

        contentTextarea.value = '';
        modal.style.display = 'flex';
        contentTextarea.focus();
    }

    /**
     * Close note modal
     */
    function closeNoteModal() {
        document.getElementById('note-modal').style.display = 'none';
        pendingAnnotation = null;

        // Clear text selection
        if (window.getSelection) {
            window.getSelection().removeAllRanges();
        }
    }

    /**
     * Save note from modal
     */
    async function saveNote() {
        const content = document.getElementById('note-content').value.trim();
        const color = document.getElementById('note-color').value;

        if (!content) {
            alert('Please enter a note');
            return;
        }

        try {
            let response;

            if (pendingAnnotation) {
                // Create annotation with note
                response = await fetch(`/api/books/${bookId}/annotations`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chapter_index: pendingAnnotation.chapter_index,
                        start_position: pendingAnnotation.start_position,
                        end_position: pendingAnnotation.end_position,
                        text: pendingAnnotation.text,
                        color: color,
                        note: content
                    })
                });
            } else {
                // Create standalone note
                response = await fetch(`/api/books/${bookId}/notes`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        chapter_index: currentChapter,
                        position_in_chapter: 0,
                        content: content,
                        color: color
                    })
                });
            }

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            closeNoteModal();

            // Reload notes if sidebar is open
            if (!document.getElementById('notes-sidebar').classList.contains('closed')) {
                await loadNotes();
            }

            // Reload annotations
            await loadAnnotations();

            alert('Note saved!');
        } catch (error) {
            console.error('Failed to save note:', error);
            alert('Failed to save note: ' + error.message);
        }
    }

    /**
     * Navigate to note location
     */
    async function navigateToNote(noteId) {
        const note = notes.find(n => n.id === noteId);
        if (note) {
            await loadChapter(note.chapter_index);
            toggleNotes();
        }
    }

    /**
     * Delete note
     */
    async function deleteNote(noteId) {
        if (!confirm('Delete this note?')) return;

        try {
            const response = await fetch(`/api/notes/${noteId}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            await loadNotes();
        } catch (error) {
            console.error('Failed to delete note:', error);
            alert('Failed to delete note');
        }
    }

    // ============================================
    // ANNOTATION FUNCTIONS
    // ============================================

    /**
     * Toggle annotation mode
     */
    function toggleAnnotationMode() {
        annotationMode = !annotationMode;

        const toggleBtn = document.getElementById('annotation-toggle-btn');
        const chapterText = document.getElementById('chapter-text');

        if (annotationMode) {
            toggleBtn.classList.add('active');
            chapterText.classList.add('annotation-mode');
            chapterText.style.cursor = 'text';
        } else {
            toggleBtn.classList.remove('active');
            chapterText.classList.remove('annotation-mode');
            chapterText.style.cursor = 'default';

            // Clear any pending annotation
            pendingAnnotation = null;
        }
    }

    /**
     * Load annotations for current chapter
     */
    async function loadAnnotations() {
        try {
            const response = await fetch(`/api/books/${bookId}/annotations?chapter_index=${currentChapter}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            annotations = data.annotations;

            renderAnnotations();
        } catch (error) {
            console.error('Failed to load annotations:', error);
        }
    }

    /**
     * Render annotations in text
     */
    function renderAnnotations() {
        // For now, annotations are stored but not visually rendered in the text
        // A full implementation would require wrapping text spans with highlight markers
        // This is a complex feature that would need careful DOM manipulation
    }

    // ============================================
    // ZOOM FUNCTIONS
    // ============================================

    /**
     * Apply current zoom level to content
     */
    function applyZoom() {
        const content = document.getElementById('chapter-text');
        if (content) {
            content.style.fontSize = `${currentZoom}%`;
        }

        // Update zoom level display
        const zoomLevel = document.getElementById('zoom-level');
        if (zoomLevel) {
            zoomLevel.textContent = `${currentZoom}%`;
        }
    }

    /**
     * Zoom in
     */
    function zoomIn() {
        const step = 10;
        currentZoom = Math.min(currentZoom + step, 200);
        applyZoom();
        localStorage.setItem('reader-zoom', currentZoom.toString());
    }

    /**
     * Zoom out
     */
    function zoomOut() {
        const step = 10;
        currentZoom = Math.max(currentZoom - step, 50);
        applyZoom();
        localStorage.setItem('reader-zoom', currentZoom.toString());
    }

    // ============================================
    // THEME FUNCTION
    // ============================================

    /**
     * Set reader theme
     * @param {string} theme - Theme name (day, sepia, night)
     */
    function setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('reader-theme', theme);

        // Update theme selector
        const themeSelector = document.getElementById('theme-selector');
        if (themeSelector) {
            themeSelector.value = theme;
        }
    }

    // Export public API
    window.readerApp = {
        init,
        loadChapter,
        prevChapter,
        nextChapter,
        toggleSummary,
        generateSummary,
        regenerateSummary,
        loadTOC,
        loadBookmarks,
        loadNotes,
        toggleAnnotationMode,
        zoomIn,
        zoomOut,
        setTheme,
        get currentChapter() { return currentChapter; },
        get totalChapters() { return totalChapters; },
        get currentChapterText() { return currentChapterText; }
    };

    // Also expose utility functions to global scope for onclick handlers
    window.navigateChapter = navigateToChapter;
    window.addBookmark = addBookmark;
    window.deleteBookmark = deleteBookmark;
    window.navigateToBookmark = navigateToBookmark;
    window.showNoteModal = showNoteModal;
    window.closeNoteModal = closeNoteModal;
    window.saveNote = saveNote;
    window.navigateToNote = navigateToNote;
    window.deleteNote = deleteNote;
    window.zoomIn = zoomIn;
    window.zoomOut = zoomOut;
    window.setTheme = setTheme;

})();

// ============================================
// JUMP TO POSITION
// ============================================

function jumpToPosition(event) {
    if (!window.readerApp) return;

    const container = event.currentTarget;
    const rect = container.getBoundingClientRect();
    const clickX = event.clientX - rect.left;
    const percentage = clickX / rect.width;

    const totalChapters = window.readerApp.totalChapters;
    const currentChapter = window.readerApp.currentChapter;

    const targetChapter = Math.floor(percentage * totalChapters);
    const clampedChapter = Math.max(0, Math.min(targetChapter, totalChapters - 1));

    if (clampedChapter !== currentChapter) {
        window.readerApp.loadChapter(clampedChapter);
    }
}

// ============================================
// TTS SPEED UPDATE
// ============================================

function updateRate(rate) {
    localStorage.setItem('reader-speed', rate);
    if (window.tts) {
        window.tts.setRate(parseFloat(rate));
    }
}

// ============================================
// TTS VOICE SELECTOR
// ============================================

let availableVoices = [];
let selectedVoice = null;

/**
 * Initialize voice selector when voices are loaded
 */
function initializeVoiceSelector() {
    const voiceSelector = document.getElementById('voice-selector');
    if (!voiceSelector) return;

    // Try to get voices immediately
    loadVoices();

    // Also listen for voiceschanged event (Firefox)
    if (speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = loadVoices;
    }
}

/**
 * Load available voices and populate selector
 */
function loadVoices() {
    const voiceSelector = document.getElementById('voice-selector');
    if (!voiceSelector) return;

    availableVoices = speechSynthesis.getVoices();

    if (availableVoices.length === 0) {
        voiceSelector.innerHTML = '<option value="">No voices available</option>';
        return;
    }

    // Get saved voice preference
    const savedVoice = localStorage.getItem('reader-voice');

    // Clear existing options
    voiceSelector.innerHTML = '';

    // Group voices by language
    const voicesByLang = {};
    availableVoices.forEach((voice, index) => {
        const lang = voice.lang.split('-')[0];
        if (!voicesByLang[lang]) {
            voicesByLang[lang] = [];
        }
        voicesByLang[lang].push({ voice, index });
    });

    // Create optgroups for each language
    Object.keys(voicesByLang).sort().forEach(lang => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = lang.toUpperCase();

        voicesByLang[lang].forEach(({ voice, index }) => {
            const option = document.createElement('option');
            option.value = index;
            option.textContent = `${voice.name} (${voice.lang})`;
            option.setAttribute('data-lang', voice.lang);

            // Set selected if this is the saved voice
            if (savedVoice && (voice.name === savedVoice || index === parseInt(savedVoice))) {
                option.selected = true;
                selectedVoice = voice;
            }

            optgroup.appendChild(option);
        });

        voiceSelector.appendChild(optgroup);
    });

    // Set initial selected voice if not set
    if (!selectedVoice && availableVoices.length > 0) {
        selectedVoice = availableVoices[0];
    }
}

/**
 * Update voice when selection changes
 */
function updateVoice(voiceIndex) {
    const voiceSelector = document.getElementById('voice-selector');
    if (!voiceSelector) return;

    const index = parseInt(voiceIndex);
    if (!isNaN(index) && availableVoices[index]) {
        selectedVoice = availableVoices[index];
        localStorage.setItem('reader-voice', selectedVoice.name);

        // Update TTS if it exists
        if (window.tts && window.tts.setVoice) {
            window.tts.setVoice(selectedVoice);
        }
    }
}

/**
 * Update voice status indicator
 */
function updateVoiceStatus(isSpeaking) {
    const voiceStatus = document.getElementById('voice-status');
    if (!voiceStatus) return;

    if (isSpeaking) {
        voiceStatus.classList.add('speaking');
    } else {
        voiceStatus.classList.remove('speaking');
    }
}

// ============================================
// KEYBOARD SHORTCUTS MODAL
// ============================================

/**
 * Toggle keyboard shortcuts modal
 */
function toggleShortcutsModal() {
    const modal = document.getElementById('shortcuts-modal');
    if (!modal) return;

    if (modal.classList.contains('show')) {
        modal.classList.remove('show');
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    } else {
        modal.style.display = 'flex';
        // Trigger reflow
        modal.offsetHeight;
        modal.classList.add('show');
    }
}

/**
 * Close shortcuts modal on overlay click
 */
function closeShortcutsModalOnOverlay(event) {
    if (event.target.id === 'shortcuts-modal') {
        toggleShortcutsModal();
    }
}

// ============================================
// NAVIGATION FUNCTIONS
// ============================================

function goToLibrary() {
    window.location.href = '/';
}

function toggleContents() {
    const sidebar = document.getElementById('contents-sidebar');
    const isClosed = sidebar.classList.contains('closed');

    // Close other sidebars
    document.getElementById('bookmarks-sidebar').classList.add('closed');
    document.getElementById('notes-sidebar').classList.add('closed');

    if (isClosed) {
        sidebar.classList.remove('closed');
        window.readerApp.loadTOC();
    } else {
        sidebar.classList.add('closed');
    }
}

function toggleBookmarks() {
    const sidebar = document.getElementById('bookmarks-sidebar');
    const isClosed = sidebar.classList.contains('closed');

    // Close other sidebars
    document.getElementById('contents-sidebar').classList.add('closed');
    document.getElementById('notes-sidebar').classList.add('closed');

    if (isClosed) {
        sidebar.classList.remove('closed');
        window.readerApp.loadBookmarks();
    } else {
        sidebar.classList.add('closed');
    }
}

function toggleNotes() {
    const sidebar = document.getElementById('notes-sidebar');
    const isClosed = sidebar.classList.contains('closed');

    // Close other sidebars
    document.getElementById('contents-sidebar').classList.add('closed');
    document.getElementById('bookmarks-sidebar').classList.add('closed');

    if (isClosed) {
        sidebar.classList.remove('closed');
        window.readerApp.loadNotes();
    } else {
        sidebar.classList.add('closed');
    }
}

function toggleAnnotationMode() {
    // Call the internal function from readerApp
    if (window.readerApp && typeof window.readerApp.toggleAnnotationMode === 'function') {
        window.readerApp.toggleAnnotationMode();
    }
}

function toggleSearch() {
    alert('Search in book coming soon!');
}

function toggleSettings() {
    alert('Settings panel coming soon!');
}

function toggleHelp() {
    alert('Reader help:\n\n• Arrow keys: Navigate chapters\n• Escape: Close panels\n• +/- keys: Zoom in/out\n• F: Toggle fullscreen\n• S: Toggle summary\n• T: Toggle TTS\n• Ctrl+B: Toggle annotation mode\n• Select text to create notes');
}

// ============================================
// FULLSCREEN TOGGLE
// ============================================

function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch((err) => {
            console.error('Failed to enter fullscreen:', err);
        });
    } else {
        document.exitFullscreen();
    }
}
