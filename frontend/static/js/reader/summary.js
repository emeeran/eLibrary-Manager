/**
 * Reader: AI summarization (chapter + full book), summary formatting, and
 * AI provider management (status, test, key/url persistence).
 */

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
