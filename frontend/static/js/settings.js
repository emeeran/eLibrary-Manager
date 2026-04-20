// Settings Page JavaScript for eBook Manager

// Current active tab
let currentTab = 'general';

/**
 * Initialize settings page
 */
document.addEventListener('DOMContentLoaded', () => {
    // Load saved settings
    loadSettings();

    // Initialize TTS voices
    loadVoices();

    // Initialize theme selection
    initializeThemeSelection();

    // Apply active class to first nav item
    document.querySelector('.settings-nav-item').classList.add('active');
});

/**
 * Switch between settings tabs
 */
function switchTab(tabId) {
    currentTab = tabId;

    // Update nav items
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.tab === tabId) {
            item.classList.add('active');
        }
    });

    // Update panels
    document.querySelectorAll('.settings-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.getElementById(`panel-${tabId}`).classList.add('active');
}

/**
 * Load settings from localStorage and server
 */
async function loadSettings() {
    // Server is source of truth — load from API first
    try {
        const response = await fetch('/api/settings');
        if (response.ok) {
            const serverSettings = await response.json();
            applySettingsToUI(serverSettings);
            return;
        }
    } catch (error) {
        console.error('Failed to load settings from server:', error);
    }

    // Fallback: load from localStorage if server unavailable
    const savedSettings = JSON.parse(localStorage.getItem('dawnstar-settings') || '{}');
    if (Object.keys(savedSettings).length > 0) {
        applySettingsToUI(savedSettings);
    }
}

/**
 * Apply settings to UI elements
 * Maps snake_case API keys to kebab-case HTML element IDs
 */
function applySettingsToUI(settings) {
    const keyToId = {
        library_path: 'library-path',
        auto_scan: 'auto-scan',
        watch_changes: 'watch-changes',
        page_layout: 'page-layout',
        text_align: 'text-align',
        font_size: 'font-size',
        font_family: 'font-family',
        line_height: 'line-height',
        theme: 'theme',
        tts_speed: 'tts-speed',
        tts_pitch: 'tts-pitch',
        ai_provider: 'ai-provider',
        ollama_url: 'ollama-url',
        auto_flip: 'auto-flip',
        flip_interval: 'flip-interval',
        summary_length: 'summary-length',
        auto_summary: 'auto-summary',
        nas_enabled: 'nas-enabled',
        nas_host: 'nas-host',
        nas_share: 'nas-share',
        nas_mount_path: 'nas-mount-path',
        nas_protocol: 'nas-protocol',
        nas_username: 'nas-username',
        nas_auto_mount: 'nas-auto-mount',
    };

    Object.entries(keyToId).forEach(([key, elemId]) => {
        if (settings[key] === undefined) return;
        const element = document.getElementById(elemId);
        if (!element) return;

        if (element.type === 'checkbox') {
            element.checked = settings[key];
        } else {
            element.value = settings[key];
        }
    });

    // Theme needs special handling (select by data attribute, not input value)
    if (settings.theme) {
        selectTheme(settings.theme);
    }
    // Update derived displays
    if (settings.font_size) {
        updateFontSizeDisplay(settings.font_size);
    }
    if (settings.tts_pitch) {
        updatePitchDisplay(settings.tts_pitch);
    }
    if (settings.ai_provider) {
        updateAIProviderSettings();
    }
}

/**
 * Save all settings
 */
async function saveSettings(event) {
    const submitButton = event ? event.submitter : null;

    // Set loading state on button
    if (submitButton) {
        setButtonLoading(submitButton, true);
    }

    const settings = {
        library_path: document.getElementById('library-path').value,
        auto_scan: document.getElementById('auto-scan').checked,
        watch_changes: document.getElementById('watch-changes').checked,
        page_layout: document.getElementById('page-layout').value,
        text_align: document.getElementById('text-align').value,
        font_size: parseInt(document.getElementById('font-size').value),
        font_family: document.getElementById('font-family').value,
        line_height: document.getElementById('line-height').value,
        theme: document.querySelector('.theme-option.selected')?.dataset.theme || 'day',
        tts_speed: document.getElementById('tts-speed').value,
        tts_pitch: parseFloat(document.getElementById('tts-pitch').value),
        ai_provider: document.getElementById('ai-provider').value,
        ai_api_key: document.getElementById('ai-api-key').value,
        ollama_url: document.getElementById('ollama-url').value,
        auto_flip: document.getElementById('auto-flip').checked,
        flip_interval: parseInt(document.getElementById('flip-interval').value),
        summary_length: document.getElementById('summary-length').value,
        auto_summary: document.getElementById('auto-summary').checked,
        // NAS settings
        nas_enabled: document.getElementById('nas-enabled').checked,
        nas_host: document.getElementById('nas-host').value,
        nas_share: document.getElementById('nas-share').value,
        nas_mount_path: document.getElementById('nas-mount-path').value,
        nas_protocol: document.getElementById('nas-protocol').value,
        nas_username: document.getElementById('nas-username').value,
        nas_password: document.getElementById('nas-password').value,
        nas_auto_mount: false
    };

    // Save to localStorage
    localStorage.setItem('dawnstar-settings', JSON.stringify(settings));

    // Also save individual settings for use in other pages
    localStorage.setItem('reader-theme', settings.theme);
    localStorage.setItem('reader-zoom', settings.font_size.toString());
    localStorage.setItem('reader-speed', settings.tts_speed);

    // Save to server
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });

        if (response.ok) {
            showNotification('Settings saved successfully!', 'success');
        } else {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to save settings');
        }
    } catch (error) {
        console.error('Failed to save settings:', error);
        showNotification('Settings saved locally. Could not sync with server: ' + error.message, 'warning');
    } finally {
        if (submitButton) {
            setButtonLoading(submitButton, false);
        }
    }
}

/**
 * Set button loading state
 */
function setButtonLoading(button, isLoading) {
    if (!button) return;

    if (isLoading) {
        button.classList.add('loading');
        button.disabled = true;
        const originalText = button.textContent;
        button.dataset.originalText = originalText;
        button.innerHTML = '<span class="btn-text" style="visibility: hidden;">' + originalText + '</span>';
    } else {
        button.classList.remove('loading');
        button.disabled = false;
        const originalText = button.dataset.originalText || 'Save Settings';
        button.textContent = originalText;
        delete button.dataset.originalText;
    }
}

/**
 * Reset settings to defaults
 */
function resetSettings() {
    if (!confirm('Are you sure you want to reset all settings to defaults?')) {
        return;
    }

    localStorage.removeItem('dawnstar-settings');

    // Reset form elements to defaults
    document.getElementById('library-path').value = '/home/user/ebooks';
    document.getElementById('auto-scan').checked = false;
    document.getElementById('watch-changes').checked = false;
    document.getElementById('page-layout').value = 'single';
    document.getElementById('text-align').value = 'justify';
    document.getElementById('font-size').value = 100;
    document.getElementById('font-family').value = 'georgia';
    document.getElementById('line-height').value = '1.8';
    document.getElementById('tts-speed').value = '1.0';
    document.getElementById('tts-pitch').value = 1;
    document.getElementById('auto-flip').checked = false;
    document.getElementById('flip-interval').value = 30;

    updateFontSizeDisplay(100);
    updatePitchDisplay(1);
    selectTheme('day');

    showNotification('Settings reset to defaults', 'info');
}

/**
 * Reset hotkeys to defaults
 */
function resetHotkeys() {
    if (!confirm('Reset all keyboard shortcuts to defaults?')) {
        return;
    }
    showNotification('Hotkeys reset to defaults', 'info');
}

/**
 * Load available TTS voices
 */
async function loadVoices() {
    const engineSelect = document.getElementById('tts-engine');
    const savedEngine = localStorage.getItem('tts-engine') || 'edgetts';
    engineSelect.value = savedEngine;
    const currentEngine = engineSelect.value || 'edgetts';

    if (currentEngine === 'gtts') {
        await loadGTVoices();
    } else if (currentEngine === 'edgetts') {
        await loadEdgeVoices();
    } else {
        loadWebSpeechVoices();
    }
}

/**
 * Load Web Speech API voices (browser TTS)
 */
function loadWebSpeechVoices() {
    const voiceSelect = document.getElementById('tts-voice');

    const populateVoices = () => {
        const voices = speechSynthesis.getVoices();
        voiceSelect.innerHTML = '<option value="">Select a voice...</option>';

        // Group voices by language
        const voicesByLang = {};
        voices.forEach((voice) => {
            const lang = voice.lang.split('-')[0];
            if (!voicesByLang[lang]) voicesByLang[lang] = [];
            voicesByLang[lang].push(voice);
        });

        // Sort languages alphabetically
        Object.keys(voicesByLang).sort().forEach(lang => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = lang.toUpperCase();
            voicesByLang[lang].forEach((voice) => {
                const option = document.createElement('option');
                option.value = `webspeech:${voice.name}`;
                option.textContent = `${voice.name} (${voice.lang})`;
                optgroup.appendChild(option);
            });
            voiceSelect.appendChild(optgroup);
        });
    };

    populateVoices();
    if (speechSynthesis.onvoiceschanged !== undefined) {
        speechSynthesis.onvoiceschanged = populateVoices;
    }
}

/**
 * Load EdgeTTS voices from server
 */
async function loadEdgeVoices() {
    const voiceSelect = document.getElementById('tts-voice');
    voiceSelect.innerHTML = '<option value="">Loading voices...</option>';

    try {
        const response = await fetch('/api/tts/voices?engine=edgetts');
        if (!response.ok) throw new Error('Failed to load voices');

        const data = await response.json();
        const voices = data.voices || [];

        voiceSelect.innerHTML = '<option value="">Select a voice...</option>';

        // Group voices by locale
        const voicesByLocale = {};
        voices.forEach((voice) => {
            const locale = voice.locale;
            if (!voicesByLocale[locale]) voicesByLocale[locale] = [];
            voicesByLocale[locale].push(voice);
        });

        // Sort locales alphabetically
        Object.keys(voicesByLocale).sort().forEach(locale => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = locale.toUpperCase();
            voicesByLocale[locale].forEach((voice) => {
                const option = document.createElement('option');
                option.value = `edgetts:${voice.id}`;
                option.textContent = voice.name;
                if (voice.id === data.default_voice) {
                    option.selected = true;
                }
                optgroup.appendChild(option);
            });
            voiceSelect.appendChild(optgroup);
        });

    } catch (error) {
        console.error('Failed to load EdgeTTS voices:', error);
        voiceSelect.innerHTML = '<option value="">Failed to load voices</option>';
    }
}

/**
 * Load gTTS voices/languages from server
 */
async function loadGTVoices() {
    const voiceSelect = document.getElementById('tts-voice');
    voiceSelect.innerHTML = '<option value="">Loading voices...</option>';

    try {
        const response = await fetch('/api/tts/voices?engine=gtts');
        if (!response.ok) throw new Error('Failed to load voices');

        const data = await response.json();
        const voices = data.voices || [];

        voiceSelect.innerHTML = '<option value="">Select a language...</option>';

        // Group voices by locale
        const voicesByLocale = {};
        voices.forEach((voice) => {
            const locale = voice.Locale.split('-')[0];
            if (!voicesByLocale[locale]) voicesByLocale[locale] = [];
            voicesByLocale[locale].push(voice);
        });

        // Sort locales alphabetically
        Object.keys(voicesByLocale).sort().forEach(locale => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = locale.toUpperCase();
            voicesByLocale[locale].forEach((voice) => {
                const option = document.createElement('option');
                option.value = `gtts:${voice.ShortName}`;
                option.textContent = voice.FriendlyName;
                if (voice.ShortName === data.default_voice) {
                    option.selected = true;
                }
                optgroup.appendChild(option);
            });
            voiceSelect.appendChild(optgroup);
        });

    } catch (error) {
        console.error('Failed to load gTTS voices:', error);
        voiceSelect.innerHTML = '<option value="">Failed to load voices</option>';
    }
}

/**
 * Change TTS engine
 */
function changeTTSEngine(engine) {
    localStorage.setItem('tts-engine', engine);
    loadVoices();

    // Show/hide pitch control (only for Web Speech and EdgeTTS)
    const pitchRow = document.getElementById('tts-pitch')?.closest('.setting-row');
    if (pitchRow) {
        pitchRow.style.display = engine === 'gtts' ? 'none' : 'flex';
    }
}

/**
 * Test TTS with current settings
 */
async function testTTS() {
    const engine = document.getElementById('tts-engine').value;
    const voice = document.getElementById('tts-voice').value;
    const speed = document.getElementById('tts-speed').value;
    const pitch = document.getElementById('tts-pitch').value;

    const testText = "This is a test of the text to speech feature. You should be hearing this in the language you selected.";

    if (engine === 'gtts' || engine === 'edgetts') {
        // Test with server-side TTS
        try {
            const voiceId = voice.replace(`${engine}:`, '');
            const engineName = engine === 'edgetts' ? 'edgetts' : 'gtts';

            const response = await fetch('/api/tts/synthesize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: testText,
                    voice: voiceId,
                    rate: speed,
                    pitch: '+0Hz',
                    engine: engineName
                })
            });

            if (!response.ok) throw new Error('TTS synthesis failed');

            const audioBlob = await response.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            await audio.play();

            // Check which engine actually generated the audio
            const actualEngine = response.headers.get('X-TTS-Engine');
            if (actualEngine && actualEngine !== engineName) {
                console.log(`TTS fell back from ${engineName} to ${actualEngine}`);
            }

        } catch (error) {
            console.error(`${engine} test failed:`, error);
            alert(`Failed to test ${engine}: ` + error.message);
        }
    } else {
        // Test with Web Speech API
        const utterance = new SpeechSynthesisUtterance(testText);

        if (voice && voice !== 'default') {
            const voices = speechSynthesis.getVoices();
            const voiceIndex = parseInt(voice.replace('webspeech:', ''));
            if (voices[voiceIndex]) {
                utterance.voice = voices[voiceIndex];
            }
        }

        utterance.rate = parseFloat(speed);
        utterance.pitch = parseFloat(pitch);

        speechSynthesis.speak(utterance);
    }
}

/**
 * Initialize theme selection
 */
function initializeThemeSelection() {
    const savedTheme = localStorage.getItem('reader-theme') || 'day';
    selectTheme(savedTheme);
}

/**
 * Select a theme
 */
function selectTheme(theme) {
    document.querySelectorAll('.theme-option').forEach(option => {
        option.classList.remove('selected');
        if (option.dataset.theme === theme) {
            option.classList.add('selected');
        }
    });
}

/**
 * Update font size display
 */
function updateFontSizeDisplay(value) {
    document.getElementById('font-size-display').textContent = `${value}%`;
}

/**
 * Update pitch display
 */
function updatePitchDisplay(value) {
    document.getElementById('pitch-display').textContent = parseFloat(value).toFixed(1);
}

/**
 * Update AI provider settings visibility
 */
function updateAIProviderSettings() {
    const provider = document.getElementById('ai-provider').value;
    const ollamaRow = document.getElementById('ollama-url-row');

    if (provider === 'ollama') {
        ollamaRow.style.display = 'flex';
    } else {
        ollamaRow.style.display = 'none';
    }
}

/**
 * Browse for library path
 */
function browseLibraryPath() {
    showNotification('Please enter the path manually. Path browsing is not available in web interface.', 'info');
    document.getElementById('library-path').focus();
}

/**
 * Test AI connection
 */
async function testAIConnection(event) {
    const provider = document.getElementById('ai-provider').value;
    const apiKey = document.getElementById('ai-api-key').value;

    if (!apiKey && provider !== 'ollama') {
        showNotification('Please enter an API key first', 'warning');
        return;
    }

    const btn = event.target;
    const originalText = btn.textContent;
    setButtonLoading(btn, true);

    try {
        const response = await fetch('/api/settings/test-ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider, api_key: apiKey })
        });

        if (response.ok) {
            const result = await response.json();
            showNotification(`AI connection successful! Provider: ${result.provider}`, 'success');
        } else {
            const error = await response.json();
            showNotification(`Connection failed: ${error.detail || error.message}`, 'error');
        }
    } catch (error) {
        showNotification('Connection failed. Check your settings and try again.', 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

/**
 * Test NAS connection
 */
async function testNASConnection(event) {
    const btn = event.target;
    const originalText = btn.textContent;
    setButtonLoading(btn, true);

    try {
        // First save NAS settings so the test endpoint can use them
        const nasSettings = {
            nas_enabled: document.getElementById('nas-enabled').checked,
            nas_host: document.getElementById('nas-host').value,
            nas_share: document.getElementById('nas-share').value,
            nas_mount_path: document.getElementById('nas-mount-path').value,
            nas_protocol: document.getElementById('nas-protocol').value,
            nas_username: document.getElementById('nas-username').value,
            nas_password: document.getElementById('nas-password').value,
        };

        // Save settings first
        await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(nasSettings)
        });

        // Then test connection
        const response = await fetch('/api/settings/test-nas', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const statusDiv = document.getElementById('nas-status');
        const statusDot = document.getElementById('nas-status-dot');
        const statusText = document.getElementById('nas-status-text');
        statusDiv.style.display = 'block';

        if (response.ok) {
            const result = await response.json();
            statusDot.style.backgroundColor = '#4CAF50';
            statusText.textContent = result.message;
            showNotification('NAS connection successful!', 'success');
        } else {
            const error = await response.json();
            statusDot.style.backgroundColor = '#f44336';
            statusText.textContent = error.detail?.message || 'Connection failed';
            showNotification('NAS connection failed: ' + (error.detail?.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        showNotification('NAS test failed: ' + error.message, 'error');
    } finally {
        setButtonLoading(btn, false);
    }
}

/**
 * Show notification to user (Enhanced with icons and close button)
 */
function showNotification(message, type = 'info', duration = 5000) {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;

    notification.innerHTML = `
        <span class="notification-icon"></span>
        <span class="notification-content">
            <span class="notification-message">${escapeHtml(message)}</span>
        </span>
        <button class="notification-close" aria-label="Close notification">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
            </svg>
        </button>
    `;

    document.body.appendChild(notification);

    // Close button handler
    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', () => {
        dismissNotification(notification);
    });

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
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Keyboard shortcuts for settings
document.addEventListener('keydown', (e) => {
    // Don't trigger if typing in input fields
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }

    // Escape: Return to library
    if (e.key === 'Escape') {
        window.location.href = '/';
    }

    // Ctrl/Cmd + S: Save settings
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveSettings();
    }
});
