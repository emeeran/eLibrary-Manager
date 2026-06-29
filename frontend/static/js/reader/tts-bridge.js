/**
 * Reader: TTS bridge.
 *
 * The actual audio engine lives in tts.js (loaded before the reader modules).
 * These are thin wrappers that sync IcecreamReader state with the tts.js API.
 */

/**
 * Initialize TTS - delegates voice loading to tts.js
 */
async function initializeTTS() {
    // tts.js handles its own initialization via initTTS() on DOMContentLoaded.
    // We only sync state here after tts.js has loaded.
    if (!window.tts) {
        console.warn('tts.js not loaded; TTS features unavailable.');
        return;
    }
    try {
        IcecreamReader.ttsVoices = window.tts.getVoices();
        IcecreamReader.ttsRate = window.tts.getRate();
    } catch (error) {
        console.error('Failed to initialize TTS:', error);
    }
}

/**
 * Toggle TTS on/off - thin wrapper around tts.js
 */
async function toggleTTS() {
    if (!window.tts) return;

    if (IcecreamReader.ttsPlaying || window.tts.isSpeaking() || window.tts.isLoading()) {
        stopTTS();
    } else {
        IcecreamReader.ttsEnabled = true;
        IcecreamReader.ttsPlaying = true;
        updateTTSUI();
        try {
            await window.tts.speakCurrentChapter();
        } catch (error) {
            console.error('TTS error:', error);
            showToast(`Failed to play audio: ${error.message}`);
        }
    }
}

/**
 * Stop TTS playback - thin wrapper around tts.js
 */
function stopTTS() {
    if (window.tts) {
        window.tts.stop();
    }
    IcecreamReader.ttsPlaying = false;
    IcecreamReader.ttsEnabled = false;
    updateTTSUI();
}

/**
 * Update TTS UI state - called by tts.js callback and locally.
 * Accepts optional state param from tts.js callback ('playing', 'paused', 'loading', 'idle').
 */
function updateTTSUI(state) {
    // Sync state from tts.js if available
    if (window.tts) {
        if (state === 'playing') {
            IcecreamReader.ttsEnabled = true;
            IcecreamReader.ttsPlaying = true;
        } else if (state === 'paused') {
            IcecreamReader.ttsPlaying = false;
            // keep ttsEnabled true while paused
        } else if (state === 'loading') {
            IcecreamReader.ttsEnabled = true;
            IcecreamReader.ttsPlaying = false;
        } else if (state === 'idle') {
            IcecreamReader.ttsPlaying = false;
            IcecreamReader.ttsEnabled = false;
        }
    }

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

// Expose updateTTSUI globally so tts.js can call it via window.updateTTSUI
window.updateTTSUI = updateTTSUI;
