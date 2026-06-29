/**
 * Reader: display settings (theme, zoom, fonts, spacing, margin, page layout,
 * volume, TTS speed), preference persistence, and server sync.
 */

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

    const savedFontSize = parseInt(localStorage.getItem('reader-font-size')) || 15;
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

    // Load saved margin
    const savedMargin = parseInt(localStorage.getItem('reader-margin')) || 20;
    setMargin(savedMargin);

    // Initialization complete — enable settings sync
    _initializing = false;
}

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
 * Update zoom display
 */
function updateZoomDisplay() {
    const display = document.getElementById('ic-zoom-display');
    if (display) {
        display.textContent = IcecreamReader.zoomLevel + '%';
    }
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
 * Set margin (percentage value 0-50) — controls reading area max-width.
 * @param {number} percent - Margin percentage (0 = full width, 50 = narrowest)
 */
function setMargin(percent) {
    percent = Math.max(0, Math.min(50, parseInt(percent) || 0));
    IcecreamReader.margin = percent;
    localStorage.setItem('reader-margin', percent);

    const chapterContent = document.querySelector('.ic-chapter-content');
    if (chapterContent) {
        const maxW = 100 - percent;
        chapterContent.style.setProperty('max-width', `${maxW}%`, 'important');
        chapterContent.style.setProperty('margin', '0 auto', 'important');
    }

    const display = document.getElementById('ic-margin-display');
    if (display) display.textContent = `${percent}%`;
    syncSettingsToServer();
}

/**
 * Adjust margin by delta percentage points
 * @param {number} delta - Amount to change (positive = wider margins, negative = narrower)
 */
function adjustMargin(delta) {
    const current = IcecreamReader.margin || 20;
    setMargin(current + delta);
}

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

    // Update TTS audio volume if playing (delegates to tts.js)
    if (window.tts) {
        window.tts.setVolume(value);
    }
}

/**
 * Set TTS speed - thin wrapper around tts.js
 */
function setSpeed(rate) {
    IcecreamReader.ttsRate = rate;

    const display = document.getElementById('ic-speed-display');
    if (display) {
        display.textContent = rate.toFixed(1) + 'x';
    }

    localStorage.setItem('tts-speed', rate);
    localStorage.setItem('dawnstar_tts_rate', rate.toString());

    // If currently speaking via tts.js, restart with new rate
    if (window.tts && window.tts.isSpeaking()) {
        window.tts.stop();
        setTimeout(() => window.tts.speakCurrentChapter(), 100);
    }

    const menu = document.getElementById('ic-speed-menu');
    if (menu) menu.style.display = 'none';
}
