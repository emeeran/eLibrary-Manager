/**
 * Reader: text selection, highlights/annotations, notes, and bookmarks.
 * All API-backed; annotations are re-applied to the DOM on chapter load.
 */

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

/* Bookmarks ---------------------------------------------------------- */

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
