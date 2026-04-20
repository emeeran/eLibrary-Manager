// Library Page JavaScript for eBook Manager
// Pixel-Perfect Icecream UI Clone

let currentPage = 1;
const pageSize = 24;
let currentFilters = {};
let currentView = 'grid';
let totalBooks = 0;
let isLoadingMore = false;

// Precomputed SVG icons (avoid rebuilding strings per book)
const SVG_EDIT = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>';
const SVG_IMAGE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>';
const SVG_DELETE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>';
const SVG_TAG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M17.63 5.84C17.27 5.33 16.67 5 16 5L5 5.01C3.9 5.01 3 5.9 3 7v10c0 1.1.9 1.99 2 1.99L16 19c.67 0 1.27-.33 1.63-.84L22 12l-4.37-6.16z"/></svg>';
const SVG_LOCK = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z"/></svg>';

// Fast HTML escape using lookup table
const _escMap = {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'};
const _escRe = /[&<>"']/g;
function escapeHtml(text) {
    return text.replace(_escRe, c => _escMap[c]);
}

/**
 * Load books from API
 */
async function loadBooks(append = false) {
    if (!append) showLoading();

    const params = new URLSearchParams({
        page: currentPage,
        page_size: pageSize,
        ...currentFilters
    });

    try {
        const response = await fetch(`/api/books?${params}`);
        const data = await response.json();

        totalBooks = data.total;
        renderBooks(data.books, append);
        updateCounts(data.counts);
        hideLoading();
    } catch (error) {
        console.error('Failed to load books:', error);
        showError('Failed to load books. Please try again.');
        hideLoading();
    }
}

/**
 * Load next page for infinite scroll
 */
async function loadMoreBooks() {
    if (isLoadingMore) return;
    const loadedSoFar = currentPage * pageSize;
    if (loadedSoFar >= totalBooks) return;

    isLoadingMore = true;
    currentPage++;
    await loadBooks(true);
    isLoadingMore = false;
}

/**
 * Render books to the grid or table
 */
function renderBooks(books, append = false) {
    const grid = document.getElementById('book-grid');

    if (books.length === 0 && !append) {
        // Determine which empty state to show based on current filters
        let emptyStateTitle = 'No books found';
        let emptyStateDescription = 'Try adjusting your filters or add books to get started.';
        let emptyStateIcon = '📚';
        let showPrimaryButton = true;
        let showSecondaryButton = false;

        // Check if user has any filters applied
        const hasFilters = Object.keys(currentFilters).length > 0;
        const hasSearch = currentFilters.search;

        if (hasSearch) {
            emptyStateTitle = 'No matching books';
            emptyStateDescription = `No books match "${escapeHtml(currentFilters.search)}". Try a different search term.`;
            emptyStateIcon = '🔍';
            showPrimaryButton = false;
            showSecondaryButton = true;
        } else if (hasFilters) {
            emptyStateTitle = 'No books in this category';
            emptyStateDescription = 'Try selecting a different category or add more books to your library.';
            emptyStateIcon = '📂';
            showPrimaryButton = false;
            showSecondaryButton = true;
        }

        grid.innerHTML = `
            <div class="empty-state ${currentView === 'table' ? '' : 'empty-state-library'}" style="${currentView === 'table' ? '' : 'grid-column: 1 / -1;'}">
                <div class="empty-state-icon">${emptyStateIcon}</div>
                <div class="empty-state-title">${emptyStateTitle}</div>
                <div class="empty-state-description">${emptyStateDescription}</div>
                <div class="empty-state-actions">
                    ${showPrimaryButton ? `
                        <button class="empty-state-btn empty-state-btn-primary" onclick="openAddBookModal()">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/>
                            </svg>
                            Add Book
                        </button>
                        <button class="empty-state-btn empty-state-btn-secondary" onclick="openImportModal()">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"/>
                            </svg>
                            Import Folder
                        </button>
                    ` : ''}
                    ${showSecondaryButton ? `
                        <button class="empty-state-btn empty-state-btn-secondary" onclick="clearFilters()">
                            Clear Filters
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
        return;
    }

    if (currentView === 'table') {
        renderTableView(books, append);
    } else {
        renderGridView(books, append);
    }
}

/**
 * Clear all filters
 */
function clearFilters() {
    currentFilters = {};
    currentPage = 1;
    loadBooks();
}

/**
 * Render books as grid
 */
function renderGridView(books, append = false) {
    const grid = document.getElementById('book-grid');
    grid.className = 'book-grid';

    const html = books.map(book => {
        const yearInfo = book.publish_date ? book.publish_date.substring(0, 4) : '';
        const safeTitle = escapeHtml(book.title);
        const safeAuthor = escapeHtml(book.author || 'Unknown Author');

        return `
        <div class="book-card-wrapper" role="listitem">
            <div class="book-card" data-book-id="${book.id}" tabindex="0" role="button" aria-label="Read ${safeTitle} by ${safeAuthor}">
                <div class="book-card-cover">
                    ${book.cover_path
                ? `<img src="/covers/${encodeURIComponent(book.cover_path.split('/').pop())}"
                       alt="${safeTitle}"
                       loading="lazy"
                       class="lazy-image"
                       onload="this.classList.add('loaded')"
                       onerror="this.parentElement.innerHTML='<div class=&quot;book-card-cover-placeholder&quot;>📖</div>'">`
                : '<div class="book-card-cover-placeholder" aria-hidden="true">📖</div>'
            }
                    <div class="book-card-progress">
                        <div class="book-card-progress-fill" style="width: ${book.progress || 0}%" data-progress="${Math.round(book.progress || 0)}%"></div>
                    </div>
                    ${book.is_favorite ? '<div class="book-card-favorite" aria-label="Favorite">★</div>' : ''}
                </div>
                <div class="book-card-info">
                    <div class="book-card-title" title="${safeTitle}">${safeTitle}</div>
                    <div class="book-card-author">${safeAuthor}</div>
                    <div class="book-card-rating" data-rating-group="${book.id}">
                        ${[1,2,3,4,5].map(i => `<span class="star ${i <= (book.rating || 0) ? 'filled' : ''}" data-value="${i}" data-book-id="${book.id}">&#9733;</span>`).join('')}
                    </div>
                    <div class="book-card-meta">
                        <span class="book-card-format">${book.format}</span>
                        ${book.total_pages ? `<span class="book-card-pages">${book.total_pages}p</span>` : ''}
                        ${yearInfo ? `<span class="book-card-year">${yearInfo}</span>` : ''}
                    </div>
                    ${book.categories && book.categories.length ? `<div class="book-card-categories"><span class="category-pill">${escapeHtml(book.categories[0])}</span>${book.categories.length > 1 ? `<span class="category-pill category-pill-more">+${book.categories.length - 1}</span>` : ''}</div>` : ''}
                </div>
            </div>
            <div class="book-card-actions">
                <button class="book-card-action-btn" data-action="edit" data-book-id="${book.id}" title="Edit">${SVG_EDIT}</button>
                <button class="book-card-action-btn" data-action="cover" data-book-id="${book.id}" title="Change Cover">${SVG_IMAGE}</button>
                <button class="book-card-action-btn" data-action="delete" data-book-id="${book.id}" title="Delete">${SVG_DELETE}</button>
                <button class="book-card-action-btn" data-action="category" data-book-id="${book.id}" title="Categories">${SVG_TAG}</button>
                <button class="book-card-action-btn" data-action="hide" data-book-id="${book.id}" title="Hide/Unhide">${SVG_LOCK}</button>
            </div>
        </div>
    `}).join('');

    requestAnimationFrame(() => {
        if (append) {
            grid.insertAdjacentHTML('beforeend', html);
        } else {
            grid.innerHTML = html;
        }
        initializeKeyboardNavigation();
    });
}

/**
 * Set book rating (1-5 stars, 0 to clear)
 */
async function setRating(bookId, rating) {
    const container = document.querySelector(`.book-card-rating .star[data-book-id="${bookId}"]`)?.parentElement;
    if (!container) return;

    // Optimistic update
    container.querySelectorAll('.star').forEach(s => {
        const val = parseInt(s.dataset.value);
        s.classList.toggle('filled', val <= rating);
    });

    try {
        await fetch(`/api/books/${bookId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rating })
        });
    } catch (e) {
        console.error('Failed to save rating:', e);
        // Revert on failure
        loadBooks();
    }
}

/**
 * Upload a new cover image for a book
 */
function uploadCover(bookId) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/jpeg,image/png,image/webp';
    input.onchange = async () => {
        const file = input.files[0];
        if (!file) return;
        const formData = new FormData();
        formData.append('file', file);
        try {
            const res = await fetch(`/api/books/${bookId}/cover`, {
                method: 'POST',
                body: formData
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Upload failed');
            }
            const data = await res.json();
            // Update the card image immediately
            const card = document.querySelector(`.book-card[onclick*="${bookId}"]`);
            if (card) {
                const img = card.querySelector('.book-card-cover img');
                if (img) {
                    img.src = `/covers/${data.cover_path}?t=${Date.now()}`;
                }
            }
            showNotification('Cover updated!', 'success');
        } catch (e) {
            showNotification('Failed to upload cover: ' + e.message, 'error');
        }
    };
    input.click();
}

/**
 * Render books as table
 */
function tableRowHtml(book) {
    return `
        <tr class="book-table-row" onclick="openBook(${book.id})" tabindex="0" role="button" aria-label="Read ${escapeHtml(book.title)} by ${escapeHtml(book.author || 'Unknown Author')}">
            <td class="table-col-cover">
                <div class="table-cover">
                    ${book.cover_path
        ? `<img src="/covers/${encodeURIComponent(book.cover_path.split('/').pop())}" alt="${escapeHtml(book.title)}" onerror="this.src='/static/images/no-cover.svg'">`
        : '<div class="table-cover-placeholder">📖</div>'
    }
                    ${book.is_favorite ? '<span class="table-favorite">★</span>' : ''}
                </div>
            </td>
            <td class="table-col-title">
                <div class="table-title" title="${escapeHtml(book.title)}">${escapeHtml(book.title)}</div>
            </td>
            <td class="table-col-author">
                <div class="table-author" title="${escapeHtml(book.author || 'Unknown')}">${escapeHtml(book.author || 'Unknown Author')}</div>
            </td>
            <td class="table-col-format">
                <span class="table-format">${book.format}</span>
            </td>
            <td class="table-col-progress">
                <div class="table-progress-bar">
                    <div class="table-progress-fill" style="width: ${book.progress || 0}%"></div>
                </div>
                <span class="table-progress-text">${Math.round(book.progress || 0)}%</span>
            </td>
            <td class="table-col-pages">
                <span class="table-pages">${book.total_pages ? `${book.current_page || 1} / ${book.total_pages}` : '-'}</span>
            </td>
            <td class="table-col-actions">
                <div class="table-actions">
                    <button class="table-action-btn" onclick="event.stopPropagation(); openEditModal(${book.id})" title="Edit">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/>
                        </svg>
                    </button>
                    <button class="table-action-btn" onclick="event.stopPropagation(); toggleFavorite(${book.id})" title="Toggle favorite">
                        ${book.is_favorite ? '★' : '☆'}
                    </button>
                    <button class="table-action-btn table-action-delete" onclick="event.stopPropagation(); deleteBook(${book.id}, event)" title="Delete">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/>
                        </svg>
                    </button>
                </div>
            </td>
        </tr>`;
}

function renderTableView(books, append = false) {
    const grid = document.getElementById('book-grid');
    grid.className = 'book-table-container';

    if (append) {
        const tbody = grid.querySelector('tbody');
        if (tbody) {
            tbody.insertAdjacentHTML('beforeend', books.map(book => tableRowHtml(book)).join(''));
            return;
        }
    }

    grid.innerHTML = `
        <table class="book-table">
            <thead>
                <tr>
                    <th class="table-col-cover"></th>
                    <th class="table-col-title">Title</th>
                    <th class="table-col-author">Author</th>
                    <th class="table-col-format">Format</th>
                    <th class="table-col-progress">Progress</th>
                    <th class="table-col-pages">Pages</th>
                    <th class="table-col-actions">Actions</th>
                </tr>
            </thead>
            <tbody>
                ${books.map(book => tableRowHtml(book)).join('')}
            </tbody>
        </table>
    `;
}

/**
 * Update sidebar counts
 */
function updateCounts(counts) {
    if (counts) {
        document.getElementById('count-all').textContent = counts.all || 0;
        document.getElementById('count-recent').textContent = counts.recent || 0;
        document.getElementById('count-favorites').textContent = counts.favorites || 0;
        document.getElementById('count-reading').textContent = counts.reading || 0;
        document.getElementById('count-deleted').textContent = counts.deleted || 0;
        const hiddenCount = document.getElementById('count-hidden');
        if (hiddenCount) hiddenCount.textContent = counts?.hidden || 0;
    }
}

/**
 * Open a book in the reader
 */
function openBook(bookId) {
    window.location.href = `/reader/${bookId}`;
}

/**
 * Filter by category (sidebar navigation)
 */
function filterByCategory(category, event) {
    // Update active state
    document.querySelectorAll('.nav-item, .directory-item').forEach(item => item.classList.remove('active'));
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('active');
    }

    // Clear filters and apply new
    currentFilters = {};
    delete currentFilters.format_filter;

    switch (category) {
        case 'all':
            break;
        case 'recent':
            currentFilters.recent_only = true;
            break;
        case 'favorites':
            currentFilters.favorite_only = true;
            break;
        case 'reading':
            currentFilters.reading_only = true;
            break;
        case 'deleted':
            currentFilters.deleted_only = true;
            break;
        case 'hidden':
            if (!_hiddenPasswordVerified) {
                showHiddenBooks();
                return;
            }
            currentFilters.hidden_only = true;
            currentFilters.show_hidden = true;
            break;
    }

    currentPage = 1;
    loadBooks();
}

/**
 * Filter by format (submenu)
 */
function filterByFormat(format, event) {
    // Update active state
    document.querySelectorAll('.nav-subitem').forEach(item => item.classList.remove('active'));
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('active');
    }

    if (format === 'all') {
        delete currentFilters.format_filter;
    } else {
        currentFilters.format_filter = format;
    }

    currentPage = 1;
    loadBooks();
}

/**
 * Toggle format section expansion
 */
function toggleFormatSection() {
    const subitems = document.getElementById('format-subitems');
    const expandIcon = document.getElementById('format-expand-icon');

    subitems.classList.toggle('hidden');
    expandIcon.classList.toggle('expanded');
}

/**
 * Load formats from API
 */
async function loadFormats() {
    try {
        const res = await fetch('/api/library/formats');
        if (!res.ok) return;
        _formats = await res.json();
        renderFormatSidebar();
    } catch (e) {
        console.error('Failed to load formats:', e);
    }
}

/**
 * Render format items in sidebar
 */
function renderFormatSidebar() {
    const list = document.getElementById('format-list');
    if (!list) return;

    let html = `<div class="nav-subitem" onclick="filterByFormat('all', event)">All Formats</div>`;
    html += _formats.map(f => `
        <div class="nav-subitem" onclick="filterByFormat('${f.format}', event)">
            <span>${f.format}</span>
            <span class="nav-item-count">${f.book_count}</span>
        </div>
    `).join('');
    list.innerHTML = html;
}

/**
 * Toggle sidebar collapse/expand
 */
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');

    // Save state to localStorage
    localStorage.setItem('sidebar-collapsed', sidebar.classList.contains('collapsed'));
}

/**
 * Initialize sidebar state from localStorage
 */
function initializeSidebarState() {
    const collapsed = localStorage.getItem('sidebar-collapsed') === 'true';
    const sidebar = document.getElementById('sidebar');
    if (collapsed && sidebar) {
        sidebar.classList.add('collapsed');
    }
}

/**
 * Set view mode (grid/table)
 */
function setView(view) {
    currentView = view;

    // Update button states
    document.getElementById('view-grid').classList.toggle('active', view === 'grid');
    document.getElementById('view-table').classList.toggle('active', view === 'table');

    // Re-render books with new view
    loadBooks();
}

/**
 * Toggle favorite status
 */
async function toggleFavorite(bookId) {
    try {
        const response = await fetch(`/api/books/${bookId}/favorite`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to toggle favorite');

        // Reload books to update UI
        loadBooks();
    } catch (error) {
        console.error('Failed to toggle favorite:', error);
    }
}

/**
 * Open edit book modal
 */
async function openEditModal(bookId) {
    try {
        const response = await fetch(`/api/books/${bookId}`);
        if (!response.ok) throw new Error('Failed to fetch book details');
        const book = await response.json();

        // Populate edit form
        document.getElementById('edit-book-id').value = book.id;
        document.getElementById('edit-title').value = book.title;
        document.getElementById('edit-author').value = book.author || '';
        document.getElementById('edit-is-favorite').checked = book.is_favorite;

        // Show modal
        document.getElementById('edit-modal').classList.remove('hidden');
    } catch (error) {
        console.error('Failed to load book details:', error);
        showError('Failed to load book details');
    }
}

/**
 * Save book edits
 */
async function saveBookEdits(event) {
    event.preventDefault();

    const bookId = document.getElementById('edit-book-id').value;
    const title = document.getElementById('edit-title').value.trim();
    const author = document.getElementById('edit-author').value.trim();
    const isFavorite = document.getElementById('edit-is-favorite').checked;

    // Form validation
    const titleInput = document.getElementById('edit-title');
    if (!validateRequired(titleInput, 'Title is required')) {
        return;
    }

    if (!validateMinLength(titleInput, 1, 'Title must be at least 1 character')) {
        return;
    }

    setButtonLoading(event.submitter, true);

    try {
        const response = await fetch(`/api/books/${bookId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                author: author || null,
                is_favorite: isFavorite
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update book');
        }

        closeModal('edit-modal');
        showNotification('Book updated successfully', 'success');
        loadBooks();
    } catch (error) {
        console.error('Failed to update book:', error);
        showNotification(error.message, 'error');
    } finally {
        setButtonLoading(event.submitter, false);
    }
}

/**
 * Validate required field
 */
function validateRequired(input, errorMessage) {
    const value = input.value.trim();
    const formGroup = input.closest('.form-group');
    let errorElement = formGroup.querySelector('.form-error');

    if (!value) {
        input.classList.add('error');
        input.classList.remove('success');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'form-error';
            formGroup.appendChild(errorElement);
        }
        errorElement.textContent = errorMessage;
        errorElement.classList.add('show');
        return false;
    }

    input.classList.remove('error');
    input.classList.add('success');
    if (errorElement) {
        errorElement.classList.remove('show');
    }
    return true;
}

/**
 * Validate minimum length
 */
function validateMinLength(input, minLength, errorMessage) {
    const value = input.value.trim();
    const formGroup = input.closest('.form-group');
    let errorElement = formGroup.querySelector('.form-error');

    if (value.length < minLength) {
        input.classList.add('error');
        input.classList.remove('success');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'form-error';
            formGroup.appendChild(errorElement);
        }
        errorElement.textContent = errorMessage;
        errorElement.classList.add('show');
        return false;
    }

    input.classList.remove('error');
    input.classList.add('success');
    if (errorElement) {
        errorElement.classList.remove('show');
    }
    return true;
}

/**
 * Set button loading state with inline spinner
 */
function setButtonLoading(button, isLoading) {
    if (!button) return;

    if (isLoading) {
        button.classList.add('btn-loading');
        button.disabled = true;
        const originalText = button.textContent;
        button.dataset.originalText = originalText;
        button.innerHTML = '<span class="btn-loading-spinner"></span><span class="btn-text">' + originalText + '</span>';
    } else {
        button.classList.remove('btn-loading');
        button.disabled = false;
        const originalText = button.dataset.originalText || 'Save';
        button.textContent = originalText;
        delete button.dataset.originalText;
    }
}

/**
 * Initialize form validation
 */
function initializeFormValidation(form) {
    const inputs = form.querySelectorAll('input[required], textarea[required], select[required]');

    inputs.forEach(input => {
        // Add blur event for validation
        input.addEventListener('blur', () => {
            if (input.hasAttribute('required')) {
                validateRequired(input, 'This field is required');
            }
        });

        // Clear error on input
        input.addEventListener('input', () => {
            input.classList.remove('error');
            const formGroup = input.closest('.form-group');
            const errorElement = formGroup?.querySelector('.form-error');
            if (errorElement) {
                errorElement.classList.remove('show');
            }
        });
    });
}

/**
 * Delete book with confirmation
 */
async function deleteBook(bookId, event) {
    // Get the button that triggered this (if from click event)
    const button = event?.target.closest('button');
    const originalContent = button?.innerHTML;

    if (!confirm('Are you sure you want to delete this book? This action cannot be undone.')) {
        return;
    }

    // Double confirmation for extra safety
    if (!confirm('This will permanently delete the book from your library. Continue?')) {
        return;
    }

    // Show loading state on button
    if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="btn-spinner"></span>';
        button.setAttribute('aria-busy', 'true');
    }

    await deleteBookConfirmed(bookId, button, originalContent);
}

/**
 * Confirmed book deletion
 */
async function deleteBookConfirmed(bookId, button = null, originalContent = '') {
    try {
        const response = await fetch(`/api/books/${bookId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to delete book');
        }

        showNotification('Book deleted successfully', 'success');
        loadBooks();
    } catch (error) {
        console.error('Failed to delete book:', error);
        showError(error.message);

        // Restore button state on error
        if (button && originalContent) {
            button.disabled = false;
            button.innerHTML = originalContent;
            button.removeAttribute('aria-busy');
        }
    }
}

/**
 * Trigger library scan
 */
async function scanLibrary() {
    showLoading('Scanning library...');

    try {
        const response = await fetch('/api/library/scan', { method: 'POST' });
        const data = await response.json();

        if (data.scan_id) {
            trackScanProgress(data.scan_id);
        } else {
            hideLoading();
            showNotification('Scan complete', 'success');
            loadBooks();
        }
    } catch (error) {
        hideLoading();
        console.error('Scan failed:', error);
        showError('Scan failed. Please try again.');
    }
}

function trackScanProgress(scanId) {
    const progressInfo = document.getElementById('scan-progress-info');
    const progressText = document.getElementById('scan-progress-text');
    const progressFill = document.getElementById('scan-progress-fill');
    const loadingText = document.getElementById('loading-text');

    if (progressInfo) progressInfo.style.display = 'block';
    if (loadingText) loadingText.textContent = 'Scanning...';

    const evtSource = new EventSource(`/api/library/scan-progress/${scanId}`);

    evtSource.onmessage = (event) => {
        try {
            const p = JSON.parse(event.data);

            if (progressText && p.total_found > 0) {
                const pct = Math.round((p.processed / p.total_found) * 100);
                progressText.textContent = `${p.processed} / ${p.total_found} files — ${p.imported} added, ${p.skipped} skipped`;
                if (progressFill) progressFill.style.width = pct + '%';
            } else if (progressText) {
                progressText.textContent = `Found ${p.processed} files...`;
            }

            if (p.status === 'completed') {
                evtSource.close();
                if (progressInfo) progressInfo.style.display = 'none';
                hideLoading();
                showNotification(
                    `Scan complete: ${p.imported} added, ${p.skipped} skipped, ${p.errors} errors`,
                    'success'
                );
                loadBooks();
            } else if (p.status === 'failed') {
                evtSource.close();
                if (progressInfo) progressInfo.style.display = 'none';
                hideLoading();
                showError(`Scan failed: ${p.message}`);
            }
        } catch (e) {
            console.warn('Failed to parse SSE event:', e);
        }
    };

    evtSource.onerror = () => {
        evtSource.close();
        if (progressInfo) progressInfo.style.display = 'none';
        hideLoading();
        loadBooks();
    };
}

/**
 * Modal functions
 */
function openAddBookModal() {
    document.getElementById('upload-modal').classList.remove('hidden');
}

function openImportModal() {
    document.getElementById('import-modal').classList.remove('hidden');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

function openSettings() {
    window.location.href = '/settings';
}

function openHelp() {
    alert('Reader help:\n\n• Arrow keys: Navigate chapters\n• Escape: Close panels\n• +/- keys: Zoom in/out');
}

/**
 * Switch between upload methods
 */
function switchAddMethod(method) {
    const uploadGroup = document.getElementById('upload-method-group');
    const pathGroup = document.getElementById('path-method-group');
    const fileInput = document.getElementById('file-input');
    const pathInput = document.getElementById('file-path-input');
    const tabs = document.querySelectorAll('.add-method-tab');
    
    // Update tabs
    tabs.forEach(tab => {
        if (tab.dataset.method === method) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });
    
    if (method === 'upload') {
        uploadGroup.classList.remove('hidden');
        pathGroup.classList.add('hidden');
        fileInput.required = true;
        pathInput.required = false;
    } else {
        uploadGroup.classList.add('hidden');
        pathGroup.classList.remove('hidden');
        fileInput.required = false;
        pathInput.required = true;
    }
}

/**
 * Handle file upload
 */
async function handleUpload(event) {
    event.preventDefault();
    const form = event.target;
    const method = document.querySelector('.add-method-tab.active').dataset.method;

    showLoading();
    closeModal('upload-modal');

    try {
        let response;
        
        if (method === 'upload') {
            // Upload file
            const formData = new FormData(form);
            response = await fetch('/api/library/upload', {
                method: 'POST',
                body: formData
            });
        } else {
            // Import from path
            const filePath = form.file_path.value;
            response = await fetch('/api/library/import-file', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ file_path: filePath })
            });
        }

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Operation failed');
        }

        const book = await response.json();
        showNotification(`Successfully added: ${book.title}`, 'success');
        loadBooks();
    } catch (error) {
        console.error('Add book error:', error);
        showError(`Failed to add book: ${error.message}`);
    } finally {
        hideLoading();
        form.reset();
    }
}

/**
 * Handle directory import
 */
async function handleImport(event) {
    event.preventDefault();
    const form = event.target;
    const path = new FormData(form).get('path');

    showLoading('Starting import...');
    closeModal('import-modal');

    try {
        const response = await fetch('/api/library/import-dir', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ path: path })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Import failed');
        }

        const data = await response.json();

        if (data.scan_id) {
            trackScanProgress(data.scan_id);
        } else {
            showNotification(`Import complete: ${data.imported || 0} added, ${data.skipped || 0} skipped`, 'success');
            hideLoading();
            loadBooks();
        }
    } catch (error) {
        console.error('Import error:', error);
        showError(`Import failed: ${error.message}`);
        hideLoading();
    } finally {
        form.reset();
    }
}

/**
 * Render skeleton loading cards
 */
function renderSkeletons(count = 12) {
    const grid = document.getElementById('book-grid');

    if (currentView === 'table') {
        grid.className = 'book-table-container';
        grid.innerHTML = Array(count).fill(0).map(() => `
            <div class="skeleton table-skeleton-row">
                <div class="skeleton table-skeleton-cover"></div>
                <div class="skeleton table-skeleton-title"></div>
                <div class="skeleton table-skeleton-author"></div>
                <div class="skeleton table-skeleton-format"></div>
                <div class="skeleton table-skeleton-progress"></div>
                <div class="skeleton table-skeleton-pages"></div>
                <div class="skeleton table-skeleton-actions"></div>
            </div>
        `).join('');
    } else {
        grid.className = 'book-grid';
        grid.innerHTML = Array(count).fill(0).map(() => `
            <div class="book-card-wrapper" role="listitem" aria-hidden="true">
                <div class="book-card-skeleton" aria-hidden="true">
                    <div class="skeleton book-card-skeleton-cover"></div>
                    <div class="book-card-skeleton-info">
                        <div class="skeleton book-card-skeleton-title"></div>
                        <div class="skeleton book-card-skeleton-author"></div>
                        <div class="book-card-skeleton-meta">
                            <div class="skeleton book-card-skeleton-format"></div>
                            <div class="skeleton book-card-skeleton-pages"></div>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }
}

/**
 * Loading overlay functions
 */
function showLoading(text) {
    const overlay = document.getElementById('loading-overlay');
    overlay.classList.remove('hidden');
    const loadingText = document.getElementById('loading-text');
    if (loadingText && text) loadingText.textContent = text;
    // Render skeleton cards immediately for better UX
    renderSkeletons(pageSize);
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

/**
 * Show error message
 */
function showError(message) {
    // Use notification system instead of alert for better accessibility
    showNotification(message, 'error', 0, { showProgress: false });
}

/**
 * Show notification (Enhanced with icon, close button, auto-dismiss, progress bar, and actions)
 * @param {string} message - The notification message
 * @param {string} type - Notification type: 'success', 'error', 'warning', 'info'
 * @param {number} duration - Auto-dismiss duration in ms (0 to disable)
 * @param {Object} options - Additional options
 * @param {boolean} options.showProgress - Show progress bar
 * @param {Array} options.actions - Array of action buttons: [{label, onClick, primary}]
 */
function showNotification(message, type = 'info', duration = 5000, options = {}) {
    const { showProgress = false, actions = [] } = options;

    // Ensure notification container exists
    let container = document.querySelector('.notification-container');
    if (!container) {
        container = document.createElement('div');
        container.className = 'notification-container';
        container.setAttribute('role', 'status');
        container.setAttribute('aria-live', 'polite');
        container.setAttribute('aria-atomic', 'true');
        document.body.appendChild(container);
    }

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.setAttribute('role', type === 'error' ? 'alert' : 'status');
    notification.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');

    // Build notification HTML
    let html = `
        <span class="notification-icon"></span>
        <span class="notification-content">
            <span class="notification-message">${escapeHtml(message)}</span>
            ${actions.length > 0 ? `
                <div class="notification-actions">
                    ${actions.map(action => `
                        <button class="notification-action-btn ${action.primary ? 'notification-action-btn-primary' : 'notification-action-btn-secondary'}"
                                data-action-index="${actions.indexOf(action)}">
                            ${escapeHtml(action.label)}
                        </button>
                    `).join('')}
                </div>
            ` : ''}
        </span>
        <button class="notification-close" aria-label="Close notification">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
        </button>
        ${showProgress ? `
            <div class="notification-progress">
                <div class="notification-progress-fill"></div>
            </div>
        ` : ''}
    `;

    notification.innerHTML = html;
    container.appendChild(notification);

    // Close button handler
    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', () => {
        dismissNotification(notification);
    });

    // Action button handlers
    if (actions.length > 0) {
        const actionButtons = notification.querySelectorAll('.notification-action-btn');
        actionButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = parseInt(e.target.dataset.actionIndex);
                if (actions[index]?.onClick) {
                    actions[index].onClick();
                }
                dismissNotification(notification);
            });
        });
    }

    // Progress bar animation
    let progressFill;
    let progressAnimation;
    if (showProgress && duration > 0) {
        progressFill = notification.querySelector('.notification-progress-fill');
        progressFill.style.transition = `transform ${duration}ms linear`;
        requestAnimationFrame(() => {
            progressFill.style.transform = 'scaleX(0)';
        });
    }

    // Trigger animation
    requestAnimationFrame(() => {
        notification.classList.add('show');
    });

    // Auto-dismiss
    if (duration > 0) {
        setTimeout(() => {
            dismissNotification(notification);
        }, duration);
    }

    return notification;
}

/**
 * Dismiss notification with animation
 */
function dismissNotification(notification) {
    notification.classList.add('hiding');
    notification.classList.remove('show');

    setTimeout(() => {
        if (notification.parentElement) {
            notification.remove();
        }
    }, 400);
}

/**
 * Initialize search with debouncing, clear button, and filter chips
 */
function initializeSearch() {
    const searchInput = document.getElementById('search');
    const searchClear = document.getElementById('search-clear');
    const searchLoading = document.getElementById('search-loading');
    const searchFilters = document.getElementById('search-filters');
    const filterChips = document.querySelectorAll('.search-filter-chip');

    // Track search filter type
    let searchFilterType = 'all';

    // Filter chip click handlers
    filterChips.forEach(chip => {
        chip.addEventListener('click', () => {
            filterChips.forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            searchFilterType = chip.dataset.filter;
            currentFilters.search_type = searchFilterType;

            // Trigger search with new filter
            if (searchInput.value.trim()) {
                currentPage = 1;
                loadBooks();
            }
        });
    });

    // Clear button handler
    searchClear.addEventListener('click', () => {
        searchInput.value = '';
        delete currentFilters.search;
        delete currentFilters.search_type;
        searchFilters.style.display = 'none';
        searchClear.style.display = 'none';
        searchInput.focus();
        currentPage = 1;
        loadBooks();
    });

    let timeout;

    searchInput.addEventListener('input', (e) => {
        clearTimeout(timeout);

        const searchTerm = e.target.value.trim();

        // Show/hide clear button
        searchClear.style.display = searchTerm ? 'flex' : 'none';

        // Show/hide filter chips
        searchFilters.style.display = searchTerm ? 'flex' : 'none';

        // Show loading indicator after short delay
        timeout = setTimeout(() => {
            if (searchTerm) {
                searchLoading.style.display = 'block';
                currentFilters.search = searchTerm;
                currentFilters.search_type = searchFilterType;
            } else {
                searchLoading.style.display = 'none';
                delete currentFilters.search;
                delete currentFilters.search_type;
            }
            currentPage = 1;
            loadBooks().finally(() => {
                searchLoading.style.display = 'none';
            });
        }, 300);
    });

    // Handle escape key to clear search
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && searchInput.value) {
            searchClear.click();
        }
    });
}

/**
 * Initialize format filter
 */
function initializeFormatFilter() {
    const formatSelect = document.getElementById('format-filter');

    // Add null check to prevent crash if element does not exist
    if (!formatSelect) return;
    formatSelect.addEventListener('change', (e) => {
        const format = e.target.value;
        if (format) {
            currentFilters.format_filter = format;
        } else {
            delete currentFilters.format_filter;
        }
        currentPage = 1;
        loadBooks();
    });
}

/**
 * File input display update
 */
function initializeFileInput() {
    const fileInput = document.getElementById('file-input');
    const fileDisplay = document.getElementById('file-input-display');
    const fileText = document.getElementById('file-input-text');

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            fileDisplay.classList.add('has-file');
            fileText.textContent = file.name;
        } else {
            fileDisplay.classList.remove('has-file');
            fileText.textContent = 'Drop file here or click to browse';
        }
    });
}

/**
 * Escape HTML to prevent XSS
 */
/**
 * Close modals on overlay click
 */
function initializeModalClose() {
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.classList.add('hidden');
            }
        });
    });
}

/**
 * Initialize filters from URL params
 */
function initializeFiltersFromURL() {
    const urlParams = new URLSearchParams(window.location.search);

    if (urlParams.has('favorites')) {
        currentFilters.favorite_only = true;
    }

    if (urlParams.has('recent')) {
        currentFilters.recent_only = true;
    }

    if (urlParams.has('search')) {
        currentFilters.search = urlParams.get('search');
        document.getElementById('search').value = urlParams.get('search');
    }

    if (urlParams.has('format')) {
        currentFilters.format_filter = urlParams.get('format');
        document.getElementById('format-filter').value = urlParams.get('format');
    }
}

// ============================================
// KEYBOARD NAVIGATION (Accessibility)
// ============================================

/**
 * Initialize keyboard navigation for book grid
 */
function initializeKeyboardNavigation() {
    // Remove existing listener to avoid duplicates
    document.removeEventListener('keydown', handleGridKeyboardNavigation);
    document.addEventListener('keydown', handleGridKeyboardNavigation);
}

/**
 * Handle keyboard navigation for book grid
 */
function handleGridKeyboardNavigation(e) {
    // Don't trigger if typing in input fields or modals are open
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' ||
        e.target.tagName === 'SELECT' || e.target.closest('.modal-overlay')) {
        return;
    }

    // Check if a book card is focused
    const focusedCard = document.activeElement;
    if (!focusedCard.classList.contains('book-card')) {
        return;
    }

    switch (e.key) {
        case 'ArrowRight':
            e.preventDefault();
            navigateGrid(1);
            break;
        case 'ArrowLeft':
            e.preventDefault();
            navigateGrid(-1);
            break;
        case 'ArrowDown':
            e.preventDefault();
            navigateGrid(getGridWidth());
            break;
        case 'ArrowUp':
            e.preventDefault();
            navigateGrid(-getGridWidth());
            break;
        case 'Enter':
        case ' ':
            e.preventDefault();
            focusedCard.click();
            break;
    }
}

/**
 * Get grid width (number of columns)
 */
function getGridWidth() {
    const gridContainer = document.querySelector('.book-grid-container');
    if (!gridContainer) return 1;

    const cardWidth = 200; // Approximate card width including gap
    return Math.max(1, Math.floor(gridContainer.offsetWidth / cardWidth));
}

/**
 * Navigate to adjacent card in grid
 */
function navigateGrid(direction) {
    const cards = Array.from(document.querySelectorAll('.book-card'));
    const currentIndex = cards.indexOf(document.activeElement);

    if (currentIndex === -1) {
        // No card focused, focus first one
        cards[0]?.focus();
        return;
    }

    let newIndex = currentIndex + direction;

    // Wrap navigation
    if (newIndex < 0) {
        newIndex = cards.length - 1;
    } else if (newIndex >= cards.length) {
        newIndex = 0;
    }

    cards[newIndex]?.focus();
}

/**
 * Handle Enter/Space on book cards with keyboard
 */
document.addEventListener('keydown', (e) => {
    // Handle Enter/Space on book cards
    if ((e.key === 'Enter' || e.key === ' ') &&
        document.activeElement.classList.contains('book-card')) {
        // Let the default click handler work
        // The click will be triggered by the Enter/Space key
        return;
    }
});

// ============================================
// KEYBOARD SHORTCUTS (Icecream-style)
// ============================================

document.addEventListener('keydown', (e) => {
    // Don't trigger if typing in input fields
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }

    // Ctrl/Cmd + F: Focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        document.getElementById('search').focus();
    }

    // Ctrl/Cmd + B: Toggle sidebar
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }

    // Escape: Close modals
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay').forEach(modal => {
            modal.classList.add('hidden');
        });
    }

    // Ctrl/Cmd + N: Add new book
    if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
        e.preventDefault();
        openAddBookModal();
    }
});

// ============================================
// INITIALIZATION
// ============================================

/**
 * Event delegation for book grid — single handler instead of per-card onclick
 */
function initializeGridDelegation() {
    const grid = document.getElementById('book-grid');
    if (!grid) return;

    grid.addEventListener('click', (e) => {
        // Check for action buttons first
        const actionBtn = e.target.closest('[data-action]');
        if (actionBtn) {
            e.stopPropagation();
            const action = actionBtn.dataset.action;
            const bookId = parseInt(actionBtn.dataset.bookId);
            switch (action) {
                case 'edit': openEditModal(bookId); break;
                case 'cover': uploadCover(bookId); break;
                case 'delete': deleteBook(bookId, e); break;
                case 'category': showCategoryMenu(bookId, e); break;
                case 'hide': toggleBookHidden(bookId); break;
            }
            return;
        }

        // Check for star rating
        const star = e.target.closest('.star[data-book-id]');
        if (star) {
            e.stopPropagation();
            setRating(parseInt(star.dataset.bookId), parseInt(star.dataset.value));
            return;
        }

        // Check for book card click
        const card = e.target.closest('.book-card[data-book-id]');
        if (card) {
            openBook(parseInt(card.dataset.bookId));
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    initializeFiltersFromURL();
    initializeSearch();
    initializeFormatFilter();
    initializeFileInput();
    initializeModalClose();
    initializeSidebarState();
    initializeRippleEffects();
    initializeLazyLoading();
    initializeSort();
    initializeGridDelegation();
    loadBooks();
    loadCategories();
    loadDirectories();
    loadFormats();
    initHiddenBooks();

    // Infinite scroll
    const scrollContainer = document.querySelector('.book-grid-container');
    if (scrollContainer) {
        let scrollTimer = null;
        scrollContainer.addEventListener('scroll', () => {
            clearTimeout(scrollTimer);
            scrollTimer = setTimeout(() => {
                const { scrollTop, scrollHeight, clientHeight } = scrollContainer;
                if (scrollHeight - scrollTop - clientHeight < 400) {
                    loadMoreBooks();
                }
            }, 150);
        });
    }
});

/**
 * Sort functions
 */
function changeSortOrder(value) {
    const [sortBy, sortOrder] = value.split(':');
    currentFilters.sort_by = sortBy;
    currentFilters.sort_order = sortOrder;
    localStorage.setItem('library-sort', value);
    currentPage = 1;
    loadBooks();
}

function initializeSort() {
    const saved = localStorage.getItem('library-sort') || 'added_date:desc';
    const sel = document.getElementById('sort-select');
    if (sel) {
        sel.value = saved;
        const [sortBy, sortOrder] = saved.split(':');
        currentFilters.sort_by = sortBy;
        currentFilters.sort_order = sortOrder;
    }
}

/**
 * Initialize lazy loading with Intersection Observer fallback
 * For browsers that don't support native loading="lazy"
 */
function initializeLazyLoading() {
    // Check if browser supports native lazy loading
    if ('loading' in HTMLImageElement.prototype) {
        return; // Browser supports native lazy loading
    }

    // Intersection Observer fallback for older browsers
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.classList.add('loaded');
                    observer.unobserve(img);
                }
            }
        });
    }, {
        rootMargin: '50px 0px', // Start loading 50px before viewport
        threshold: 0.01
    });

    // Observe all lazy images
    const lazyImages = document.querySelectorAll('img.lazy-image');
    lazyImages.forEach(img => {
        // Store original src in data-src for Observer
        if (!img.dataset.src && img.src) {
            img.dataset.src = img.src;
            img.src = ''; // Clear src until needed
        }
        imageObserver.observe(img);
    });
}

/**
 * Initialize ripple effects for buttons
 */
function initializeRippleEffects() {
    document.addEventListener('click', (e) => {
        const button = e.target.closest('.btn, .book-card-action-btn, .ic-toolbar-btn');
        if (!button) return;

        const ripple = document.createElement('span');
        ripple.classList.add('ripple');

        const rect = button.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;

        ripple.style.width = ripple.style.height = `${size}px`;
        ripple.style.left = `${x}px`;
        ripple.style.top = `${y}px`;

        button.appendChild(ripple);

        ripple.addEventListener('animationend', () => {
            ripple.remove();
        });
    });
}

/**
 * ========================================
 * CATEGORY FUNCTIONS
 * ========================================
 */

let _categories = [];
let _directories = [];
let _formats = [];

/**
 * Toggle category section expand/collapse
 */
function toggleCategorySection() {
    const subitems = document.getElementById('category-subitems');
    const icon = document.getElementById('category-expand-icon');
    subitems.classList.toggle('hidden');
    if (icon) {
        icon.style.transform = subitems.classList.contains('hidden') ? '' : 'rotate(180deg)';
    }
}

/**
 * Load categories from API and render in sidebar
 */
async function loadCategories() {
    try {
        const res = await fetch('/api/categories');
        if (!res.ok) return;
        _categories = await res.json();
        renderCategorySidebar();
    } catch (e) {
        console.error('Failed to load categories:', e);
    }
}

/**
 * Render categories in sidebar
 */
function renderCategorySidebar() {
    const list = document.getElementById('category-list');
    if (!list) return;

    list.innerHTML = _categories.map(cat => `
        <div class="nav-subitem category-item" onclick="filterByCategoryId(${cat.id}, event)" data-category-id="${cat.id}">
            <span class="category-dot" style="background:${cat.color}"></span>
            <span class="category-name">${escapeHtml(cat.name)}</span>
            <span class="nav-item-count">${cat.book_count}</span>
            <button class="category-delete-btn" onclick="event.stopPropagation(); deleteCategory(${cat.id})" title="Delete category">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </button>
        </div>
    `).join('');
}

/**
 * Filter books by category
 */
function filterByCategoryId(categoryId, event) {
    if (event) {
        document.querySelectorAll('.nav-item, .category-item, .directory-item').forEach(n => n.classList.remove('active'));
        if (event.currentTarget) event.currentTarget.classList.add('active');
    }
    currentFilters.category_id = categoryId;
    currentPage = 1;
    loadBooks();
}

/**
 * Prompt to create a new category
 */
async function createCategoryPrompt() {
    const name = prompt('Enter category name:');
    if (!name || !name.trim()) return;

    const colors = ['#8b5cf6', '#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#ec4899', '#06b6d4', '#f97316'];
    const color = colors[Math.floor(Math.random() * colors.length)];

    try {
        const res = await fetch('/api/categories', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name.trim(), color })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Failed to create category');
        }
        showNotification('Category created!', 'success');
        loadCategories();
    } catch (e) {
        showNotification('Failed: ' + e.message, 'error');
    }
}

/**
 * Delete a category
 */
async function deleteCategory(categoryId) {
    const cat = _categories.find(c => c.id === categoryId);
    if (!confirm(`Delete category "${cat?.name || 'this category'}"?`)) return;

    try {
        await fetch(`/api/categories/${categoryId}`, { method: 'DELETE' });
        showNotification('Category deleted', 'success');
        if (currentFilters.category_id === categoryId) {
            delete currentFilters.category_id;
            loadBooks();
        }
        loadCategories();
    } catch (e) {
        showNotification('Failed to delete category', 'error');
    }
}

/**
 * Show category assignment menu for a book
 */
async function showCategoryMenu(bookId, event) {
    event.stopPropagation();

    const existing = document.getElementById('category-menu');
    if (existing) existing.remove();

    await loadCategories();

    const menu = document.createElement('div');
    menu.id = 'category-menu';
    menu.className = 'category-context-menu';
    menu.innerHTML = _categories.map(cat => `
        <label class="category-menu-item">
            <input type="checkbox" data-category-id="${cat.id}">
            <span class="category-dot" style="background:${cat.color}"></span>
            ${escapeHtml(cat.name)}
        </label>
    `).join('') + `
        <div class="category-menu-divider"></div>
        <div class="category-menu-item category-menu-create" onclick="createCategoryPrompt(); document.getElementById('category-menu').remove();">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
            New Category
        </div>
    `;

    const card = event.target.closest('.book-card-wrapper');
    if (card) {
        const rect = card.getBoundingClientRect();
        menu.style.top = rect.bottom + 'px';
        menu.style.left = rect.left + 'px';
    }
    document.body.appendChild(menu);

    // Load current assignments
    try {
        const res = await fetch(`/api/books/${bookId}`);
        if (res.ok) {
            const book = await res.json();
            const assigned = new Set((book.categories || []).map(name => {
                const cat = _categories.find(c => c.name === name);
                return cat?.id;
            }).filter(Boolean));

            menu.querySelectorAll('input[data-category-id]').forEach(input => {
                input.checked = assigned.has(parseInt(input.dataset.categoryId));
            });
        }
    } catch (e) { /* ignore */ }

    // Handle checkbox changes
    menu.querySelectorAll('input[data-category-id]').forEach(input => {
        input.addEventListener('change', async () => {
            const checked = Array.from(menu.querySelectorAll('input:checked')).map(i => parseInt(i.dataset.categoryId));
            try {
                await fetch(`/api/books/${bookId}/categories`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ category_ids: checked })
                });
                loadCategories();
            } catch (e) {
                console.error('Failed to update categories:', e);
            }
        });
    });

    // Close on click outside
    setTimeout(() => {
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }, 10);
}

// ============================================
// DIRECTORY FUNCTIONS
// ============================================

/**
 * Toggle the directory expandable section in sidebar
 */
function toggleDirectorySection() {
    const subitems = document.getElementById('directory-subitems');
    const icon = document.getElementById('directory-expand-icon');
    subitems.classList.toggle('hidden');
    if (icon) {
        icon.style.transform = subitems.classList.contains('hidden') ? '' : 'rotate(180deg)';
    }
}

/**
 * Load directories from API
 */
async function loadDirectories() {
    try {
        const res = await fetch('/api/library/directories');
        if (!res.ok) return;
        _directories = await res.json();
        renderDirectorySidebar();
    } catch (e) {
        console.error('Failed to load directories:', e);
    }
}

/**
 * Render directory items in sidebar
 */
function renderDirectorySidebar() {
    const list = document.getElementById('directory-list');
    if (!list) return;

    if (_directories.length === 0) {
        list.innerHTML = '';
        return;
    }

    list.innerHTML = _directories.map(dir => `
        <div class="nav-subitem directory-item" onclick="filterByDirectory('${escapeHtml(dir.directory)}', event)" data-directory="${escapeHtml(dir.directory)}" title="${escapeHtml(dir.directory)}">
            <span class="directory-name">${escapeHtml(dir.name)}</span>
            <span class="nav-item-count">${dir.book_count}</span>
        </div>
    `).join('');
}

/**
 * Filter books by directory
 */
function filterByDirectory(directory, event) {
    if (event) {
        document.querySelectorAll('.nav-item, .category-item, .directory-item').forEach(n => n.classList.remove('active'));
        if (event.currentTarget) event.currentTarget.classList.add('active');
    }
    currentFilters.directory_filter = directory;
    currentPage = 1;
    loadBooks();
}

// ============================================
// HIDDEN BOOKS
// ============================================

let _hiddenPasswordVerified = false;
let _hiddenPasswordCallback = null; // Set by toggleBookHidden to intercept submit

async function initHiddenBooks() {
    try {
        const res = await fetch('/api/hidden/status');
        const data = await res.json();
        const navItem = document.getElementById('nav-hidden');
        if (navItem) {
            navItem.style.display = 'flex';
        }
    } catch (e) {
        console.error('Failed to check hidden status:', e);
    }
}

async function showHiddenBooks() {
    const modal = document.getElementById('hidden-password-modal');
    const setGroup = document.getElementById('hidden-password-set-group');
    const verifyGroup = document.getElementById('hidden-password-verify-group');

    if (_hiddenPasswordVerified) {
        filterByCategory('hidden');
        return;
    }

    try {
        const res = await fetch('/api/hidden/status');
        const data = await res.json();

        if (!data.password_set) {
            // No password set, show set password form
            setGroup.style.display = 'block';
            verifyGroup.style.display = 'none';
            modal.classList.remove('hidden');
        } else {
            // Password required
            setGroup.style.display = 'none';
            verifyGroup.style.display = 'block';
            modal.classList.remove('hidden');
        }
    } catch (e) {
        showNotification('Failed to check hidden books status', 'error');
    }
}

async function submitHiddenPassword() {
    // If a callback was set (e.g. by toggleBookHidden), delegate to it
    if (_hiddenPasswordCallback) {
        const cb = _hiddenPasswordCallback;
        _hiddenPasswordCallback = null;
        return cb();
    }

    const setGroup = document.getElementById('hidden-password-set-group');
    const verifyGroup = document.getElementById('hidden-password-verify-group');

    if (setGroup.style.display !== 'none') {
        // Setting new password
        const password = document.getElementById('hidden-password-set').value;
        if (!password) {
            showNotification('Please enter a password', 'error');
            return;
        }
        try {
            await fetch('/api/hidden/set-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });
            _hiddenPasswordVerified = true;
            closeModal('hidden-password-modal');
            showNotification('Password set successfully', 'success');
            initHiddenBooks();
            filterByCategory('hidden');
        } catch (e) {
            showNotification('Failed to set password', 'error');
        }
    } else {
        // Verifying password
        const password = document.getElementById('hidden-password-verify').value;
        if (!password) {
            showNotification('Please enter your password', 'error');
            return;
        }
        try {
            const res = await fetch('/api/hidden/verify-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });
            const data = await res.json();
            if (res.ok && data.verified) {
                _hiddenPasswordVerified = true;
                closeModal('hidden-password-modal');
                filterByCategory('hidden');
            } else {
                showNotification('Incorrect password', 'error');
            }
        } catch (e) {
            showNotification('Failed to verify password', 'error');
        }
    }
}

async function showResetHiddenPassword() {
    const verifyGroup = document.getElementById('hidden-password-verify-group');
    const setGroup = document.getElementById('hidden-password-set-group');
    const modal = document.getElementById('hidden-password-modal');
    const titleEl = modal.querySelector('.modal-title');

    // Hide verify group, show set group repurposed for current password
    verifyGroup.style.display = 'none';
    setGroup.style.display = 'block';
    document.getElementById('hidden-password-set').value = '';
    document.getElementById('hidden-password-set').placeholder = 'Enter current password';
    const setLabel = setGroup.querySelector('.form-label');
    setLabel.textContent = 'Confirm Current Password';
    const hint = setGroup.querySelector('.form-hint');
    if (hint) hint.style.display = 'none';
    titleEl.textContent = 'Reset Password';

    _hiddenPasswordCallback = async function() {
        const password = document.getElementById('hidden-password-set').value;
        if (!password) {
            showNotification('Enter your current password', 'error');
            return;
        }
        try {
            const res = await fetch('/api/hidden/reset-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password })
            });
            const data = await res.json();
            if (!res.ok) {
                showNotification(data.detail || 'Failed to reset', 'error');
                return;
            }
            _hiddenPasswordVerified = false;
            closeModal('hidden-password-modal');
            showNotification('Password reset. Set a new one to use hidden books.', 'success');
            initHiddenBooks();
        } catch (e) {
            showNotification('Failed to reset password', 'error');
        } finally {
            setLabel.textContent = 'Set Password';
            document.getElementById('hidden-password-set').placeholder = 'Enter password to protect hidden books';
            if (hint) hint.style.display = '';
            titleEl.textContent = 'Hidden Books';
        }
    };
}

async function toggleBookHidden(bookId) {
    try {
        const res = await fetch('/api/hidden/status');
        const data = await res.json();

        if (!data.password_set) {
            showNotification('Set a password first via Hidden Books in the sidebar', 'error');
            return;
        }

        const modal = document.getElementById('hidden-password-modal');
        const setGroup = document.getElementById('hidden-password-set-group');
        const verifyGroup = document.getElementById('hidden-password-verify-group');
        const titleEl = modal.querySelector('.modal-title');
        const resetLink = document.getElementById('hidden-password-reset-link');

        // Configure modal for hide/unhide verification
        setGroup.style.display = 'none';
        verifyGroup.style.display = 'block';
        const pwInput = document.getElementById('hidden-password-verify');
        pwInput.value = '';
        titleEl.textContent = 'Confirm Password';
        if (resetLink) resetLink.style.display = 'none';

        // Set callback — submitHiddenPassword will call this instead of its default logic
        _hiddenPasswordCallback = async function() {
            const password = pwInput.value;
            if (!password) {
                showNotification('Please enter your password', 'error');
                return;
            }
            try {
                const hideRes = await fetch(`/api/books/${bookId}/hide`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password })
                });
                const hideData = await hideRes.json();
                if (!hideRes.ok) {
                    showNotification(hideData.detail || 'Failed to update', 'error');
                    return;
                }
                closeModal('hidden-password-modal');
                showNotification(hideData.message, 'success');
                loadBooks();
            } catch (e) {
                showNotification('Failed to toggle hidden status', 'error');
            } finally {
                titleEl.textContent = 'Hidden Books';
                if (resetLink) resetLink.style.display = '';
            }
        };

        modal.classList.remove('hidden');
    } catch (e) {
        showNotification('Failed to check hidden status', 'error');
    }
}

async function autoCategorizeAll() {
    const btn = document.getElementById('btn-auto-categorize');
    if (!confirm('Auto-categorize all books using AI? This may take a moment.')) return;

    btn.disabled = true;
    const origHTML = btn.innerHTML;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="animation:spin 1s linear infinite"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg> 0/?';

    // Show progress toast
    const toastId = 'cat-progress-toast';
    let toast = document.getElementById(toastId);
    if (!toast) {
        toast = document.createElement('div');
        toast.id = toastId;
        toast.style.cssText = 'position:fixed;bottom:24px;right:24px;background:#1e293b;color:#f1f5f9;padding:16px 20px;border-radius:12px;z-index:10000;min-width:320px;max-width:420px;box-shadow:0 8px 32px rgba(0,0,0,0.3);font-size:13px;';
        document.body.appendChild(toast);
    }
    toast.innerHTML = '<div style="font-weight:600;margin-bottom:8px;">Auto-Categorizing...</div>'
        + '<div id="cat-progress-bar" style="height:6px;background:#334155;border-radius:3px;overflow:hidden;margin-bottom:8px;">'
        + '<div id="cat-progress-fill" style="height:100%;background:#3b82f6;border-radius:3px;width:0%;transition:width 0.3s ease;"></div></div>'
        + '<div id="cat-progress-text" style="color:#94a3b8;">Starting...</div>';
    toast.style.display = 'block';

    try {
        const res = await fetch('/api/library/auto-categorize-stream');
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const event = JSON.parse(line.slice(6));

                    if (event.type === 'start') {
                        document.getElementById('cat-progress-text').textContent = `Found ${event.total} books...`;
                    } else if (event.type === 'progress') {
                        const pct = Math.round((event.current / event.total) * 100);
                        document.getElementById('cat-progress-fill').style.width = pct + '%';
                        const catStr = event.categories.length > 0 ? event.categories.join(', ') : 'no match';
                        document.getElementById('cat-progress-text').innerHTML =
                            `<strong>${event.current}/${event.total}</strong> &mdash; `
                            + `<span style="color:#e2e8f0;">${event.book.substring(0, 40)}</span>`
                            + ` <span style="color:#3b82f6;">${catStr}</span>`;
                        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="animation:spin 1s linear infinite"><path d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg> ${event.current}/${event.total}`;
                    } else if (event.type === 'error') {
                        const pct = Math.round((event.current / event.total) * 100);
                        document.getElementById('cat-progress-fill').style.width = pct + '%';
                        document.getElementById('cat-progress-text').innerHTML =
                            `<span style="color:#f87171;">Skip:</span> ${event.book.substring(0, 40)} &mdash; ${event.error.substring(0, 50)}`;
                    } else if (event.type === 'done') {
                        document.getElementById('cat-progress-fill').style.width = '100%';
                        document.getElementById('cat-progress-text').innerHTML =
                            `<span style="color:#34d399;">Done!</span> ${event.categorized} books categorized, ${event.categories_added} categories added`;
                        setTimeout(() => { toast.style.display = 'none'; }, 5000);
                        loadBooks();
                        loadCategories();
                    }
                } catch (e) { /* skip malformed */ }
            }
        }
    } catch (e) {
        toast.style.display = 'none';
        showNotification('Auto-categorization failed — check AI settings', 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = origHTML;
    }
}
