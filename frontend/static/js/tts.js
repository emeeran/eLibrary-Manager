// Text-to-Speech Engine for eBook Manager
// Fallback strategy: EdgeTTS (default) -> Browser Web Speech API -> gTTS

(function() {
    'use strict';

    // TTS Engine types
    const ENGINE_EDGETTS = 'edgetts';
    const ENGINE_BROWSER = 'browser';
    const ENGINE_GTTS = 'gtts';

    // Engine priority order for fallback
    const ENGINE_PRIORITY = [ENGINE_EDGETTS, ENGINE_BROWSER, ENGINE_GTTS];

    // Current TTS engine
    let currentEngine = localStorage.getItem('dawnstar_tts_engine') || ENGINE_EDGETTS;
    let activeEngine = null; // The engine that successfully initialized
    let isServerLoading = false;

    // Voice storage
    let edgeTTSVoices = [];
    let gttsVoices = [];

    // Audio element for server-side TTS
    let audioElement = null;

    /**
     * Web Speech API TTS (Browser)
     * Fallback engine when server-side TTS is unavailable
     */
    class WebSpeechTTS {
        constructor() {
            this.synth = window.speechSynthesis;
            this.utterance = null;
            this.isPaused = false;
            this.currentText = '';
            this.voices = [];

            this.loadVoices();
            if (speechSynthesis.onvoiceschanged !== undefined) {
                speechSynthesis.onvoiceschanged = () => this.loadVoices();
            }
        }

        loadVoices() {
            this.voices = this.synth.getVoices() || [];
        }

        getVoices() {
            return this.voices;
        }

        speak(text, options = {}) {
            this.stop();
            this.currentText = text;
            this.utterance = new SpeechSynthesisUtterance(text);

            // Handle voice selection (can be index or voice object)
            if (options.voice) {
                if (typeof options.voice === 'number') {
                    this.utterance.voice = this.voices[options.voice] || null;
                } else if (typeof options.voice === 'object') {
                    this.utterance.voice = options.voice;
                }
            }

            this.utterance.rate = options.rate || 1.0;
            this.utterance.pitch = options.pitch || 1.0;
            this.utterance.volume = options.volume || 1.0;

            this.utterance.onstart = () => {
                updateTTSButtonState('playing');
            };
            this.utterance.onend = () => {
                updateTTSButtonState('idle');
            };
            this.utterance.onpause = () => {
                updateTTSButtonState('paused');
            };
            this.utterance.onresume = () => {
                updateTTSButtonState('playing');
            };
            this.utterance.onerror = (e) => {
                if (e.error !== 'interrupted' && e.error !== 'canceled') {
                    console.error('Browser TTS Error:', e.error);
                }
                updateTTSButtonState('idle');
            };

            startBrowserWordTracking(this.utterance);
            this.synth.speak(this.utterance);
        }

        pause() {
            if (this.synth.speaking && !this.isPaused) {
                this.synth.pause();
                this.isPaused = true;
            }
        }

        resume() {
            if (this.isPaused) {
                this.synth.resume();
                this.isPaused = false;
            }
        }

        stop() {
            this.synth.cancel();
            this.isPaused = false;
            updateTTSButtonState('idle');
            clearHighlights();
        }

        isSpeaking() {
            return this.synth.speaking && !this.isPaused;
        }

        get isPaused() {
            return this._isPaused;
        }

        set isPaused(value) {
            this._isPaused = value;
        }
    }

    /**
     * Server-side TTS (EdgeTTS or gTTS)
     * Uses fetch API to get audio from server
     */
    class ServerTTS {
        constructor(engine) {
            this.engine = engine; // 'edgetts' or 'gtts'
            this.isPlaying = false;
            this.isPaused = false;
        }

        async speak(text, options = {}) {
            this.stop();

            const voice = options.voice || null;
            const rate = options.rate || 1.0;
            const pitch = options.pitch || '+0Hz';

            try {
                isServerLoading = true;
                updateTTSButtonState('loading');

                const response = await fetch('/api/tts/synthesize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, voice, rate, pitch, engine: this.engine })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || errorData.message || 'Failed to generate speech');
                }

                // Get which engine actually generated the audio
                const actualEngine = response.headers.get('X-TTS-Engine') || this.engine;
                if (actualEngine !== this.engine) {
                    console.log(`TTS fell back from ${this.engine} to ${actualEngine}`);
                }

                // Get audio blob from response
                const blob = await response.blob();
                const audioUrl = URL.createObjectURL(blob);

                // Create and play audio element
                audioElement = new Audio(audioUrl);
                audioElement.onended = () => {
                    this.stop();
                };
                audioElement.onerror = (e) => {
                    console.error(`${this.engine} Audio Error:`, e);
                    this.stop();
                };
                audioElement.onplay = () => {
                    updateTTSButtonState('playing');
                };
                audioElement.onpause = () => {
                    if (!this.isPaused) {
                        updateTTSButtonState('idle');
                    }
                };

                audioElement.playbackRate = rate;
                await audioElement.play();
                startServerWordTracking();
                this.isPlaying = true;
                isServerLoading = false;

            } catch (error) {
                console.error(`${this.engine} TTS Error:`, error);
                isServerLoading = false;
                updateTTSButtonState('idle');
                throw error;
            }
        }

        pause() {
            if (audioElement && this.isPlaying && !this.isPaused) {
                audioElement.pause();
                this.isPaused = true;
                updateTTSButtonState('paused');
            }
        }

        resume() {
            if (this.isPaused && audioElement) {
                audioElement.play();
                this.isPaused = false;
                updateTTSButtonState('playing');
            }
        }

        stop() {
            if (audioElement) {
                audioElement.pause();
                audioElement = null;
            }
            this.isPlaying = false;
            this.isPaused = false;
            updateTTSButtonState('idle');
            clearHighlights();
        }

        isSpeaking() {
            return this.isPlaying && !this.isPaused;
        }
    }

    // Initialize TTS instances
    let webSpeechTTS = null;
    let serverTTS = null;

    /**
     * Get the best available TTS engine with fallback
     */
    function getAvailableEngine() {
        // If user explicitly selected an engine, try that first
        const preferred = currentEngine;

        // Try preferred engine first
        if (preferred === ENGINE_BROWSER) {
            if (WebSpeechTTS.isSupported()) {
                if (!webSpeechTTS) webSpeechTTS = new WebSpeechTTS();
                return { engine: ENGINE_BROWSER, tts: webSpeechTTS };
            }
        } else if (preferred === ENGINE_EDGETTS || preferred === ENGINE_GTTS) {
            // Server-side engines always available (backend handles fallback)
            if (!serverTTS || serverTTS.engine !== preferred) {
                serverTTS = new ServerTTS(preferred);
            }
            return { engine: preferred, tts: serverTTS };
        }

        // Fallback chain
        for (const engine of ENGINE_PRIORITY) {
            if (engine === ENGINE_BROWSER) {
                if (WebSpeechTTS.isSupported()) {
                    if (!webSpeechTTS) webSpeechTTS = new WebSpeechTTS();
                    return { engine: ENGINE_BROWSER, tts: webSpeechTTS };
                }
            } else {
                // Server-side engine
                if (!serverTTS) serverTTS = new ServerTTS(engine);
                return { engine, tts: serverTTS };
            }
        }

        return null;
    }

    function getTTS() {
        const available = getAvailableEngine();
        return available ? available.tts : null;
    }

    function getCurrentEngineName() {
        const available = getAvailableEngine();
        return available ? available.engine : null;
    }

    // Update TTS button state
    function updateTTSButtonState(state) {
        const btn = document.getElementById('tts-toggle-btn');
        if (!btn) return;

        btn.classList.remove('playing', 'paused', 'loading');
        if (state === 'playing') {
            btn.classList.add('playing');
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>`;
        } else if (state === 'paused') {
            btn.classList.add('paused');
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
        } else if (state === 'loading') {
            btn.classList.add('loading');
            btn.innerHTML = `<svg class="spin" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"></path></svg>`;
        } else {
            btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>`;
        }
    }

    // Load voices for server-side engines
    async function loadServerVoices(engine) {
        try {
            const response = await fetch(`/api/tts/voices?engine=${engine}`);
            const data = await response.json();
            return data.voices || [];
        } catch (error) {
            console.error(`Failed to load ${engine} voices:`, error);
            return [];
        }
    }

    // Initialize TTS UI
    async function initTTS() {
        const engineSelect = document.getElementById('tts-engine-select') || document.getElementById('tts-service-select');
        const voiceSelect = document.getElementById('voice-select');

        // Set current engine in dropdown
        if (engineSelect) {
            engineSelect.value = currentEngine;

            // Populate engine options
            const engines = [
                { id: ENGINE_EDGETTS, name: 'EdgeTTS (Neural)' },
                { id: ENGINE_BROWSER, name: 'Browser (Built-in)' },
                { id: ENGINE_GTTS, name: 'Google TTS' }
            ];

            engineSelect.innerHTML = engines.map(e =>
                `<option value="${e.id}">${e.name}</option>`
            ).join('');

            engineSelect.value = currentEngine;

            // Engine change handler
            engineSelect.addEventListener('change', async (e) => {
                currentEngine = e.target.value;
                localStorage.setItem('dawnstar_tts_engine', currentEngine);

                // Stop any current playback
                getTTS()?.stop();

                // Update voice list
                await updateVoiceList();
            });
        }

        // Load voices based on engine
        await updateVoiceList();

        // Voice change handler
        if (voiceSelect) {
            voiceSelect.addEventListener('change', (e) => {
                const engine = getCurrentEngineName();
                localStorage.setItem(`dawnstar_tts_voice_${engine}`, e.target.value);
            });
        }

        // Load saved rate preference
        const savedRate = localStorage.getItem('dawnstar_tts_rate');
        const rateInput = document.getElementById('speed-selector');
        const rateDisplay = document.getElementById('rate-display');
        if (savedRate && rateInput && rateDisplay) {
            rateInput.value = savedRate;
            rateDisplay.textContent = parseFloat(savedRate).toFixed(1);
        }

        if (rateInput) {
            rateInput.addEventListener('change', (e) => {
                const rate = parseFloat(e.target.value);
                if (rateDisplay) rateDisplay.textContent = rate.toFixed(1);
                localStorage.setItem('dawnstar_tts_rate', rate.toString());
            });
        }
    }

    // Update voice list based on current engine
    async function updateVoiceList() {
        const voiceSelect = document.getElementById('voice-select');
        if (!voiceSelect) return;

        const engine = getCurrentEngineName() || currentEngine;

        if (engine === ENGINE_EDGETTS) {
            // Load EdgeTTS voices
            if (edgeTTSVoices.length === 0) {
                edgeTTSVoices = await loadServerVoices(ENGINE_EDGETTS);
            }

            if (edgeTTSVoices.length === 0) {
                voiceSelect.innerHTML = '<option value="">No voices available</option>';
                return;
            }

            voiceSelect.innerHTML = edgeTTSVoices.map(voice =>
                `<option value="${voice.id}">${voice.name}</option>`
            ).join('');

            const savedVoice = localStorage.getItem(`dawnstar_tts_voice_${engine}`);
            const defaultVoice = edgeTTSVoices[0]?.id;
            voiceSelect.value = savedVoice || defaultVoice;

        } else if (engine === ENGINE_GTTS) {
            // Load gTTS voices
            if (gttsVoices.length === 0) {
                gttsVoices = await loadServerVoices(ENGINE_GTTS);
            }

            if (gttsVoices.length === 0) {
                voiceSelect.innerHTML = '<option value="">No voices available</option>';
                return;
            }

            voiceSelect.innerHTML = gttsVoices.map(voice =>
                `<option value="${voice.ShortName}">${voice.FriendlyName}</option>`
            ).join('');

            const savedVoice = localStorage.getItem(`dawnstar_tts_voice_${engine}`);
            const defaultVoice = gttsVoices[0]?.ShortName;
            voiceSelect.value = savedVoice || defaultVoice;

        } else {
            // Browser Web Speech API voices
            if (!webSpeechTTS) {
                webSpeechTTS = new WebSpeechTTS();
            }

            const updateVoiceList = () => {
                const voices = webSpeechTTS.getVoices();
                if (voices.length === 0) {
                    voiceSelect.innerHTML = '<option value="">Loading voices...</option>';
                    return;
                }

                // Group voices by language
                const voicesByLang = {};
                voices.forEach((voice, index) => {
                    const lang = voice.lang.split('-')[0];
                    if (!voicesByLang[lang]) voicesByLang[lang] = [];
                    voicesByLang[lang].push({ voice, index });
                });

                voiceSelect.innerHTML = '';
                Object.keys(voicesByLang).sort().forEach(lang => {
                    const optgroup = document.createElement('optgroup');
                    optgroup.label = lang.toUpperCase();
                    voicesByLang[lang].forEach(({ voice, index }) => {
                        const option = document.createElement('option');
                        option.value = index;
                        option.textContent = `${voice.name} (${voice.lang})`;
                        optgroup.appendChild(option);
                    });
                    voiceSelect.appendChild(optgroup);
                });

                const savedVoice = localStorage.getItem(`dawnstar_tts_voice_${engine}`);
                if (savedVoice !== null) {
                    voiceSelect.value = savedVoice;
                }
            };

            updateVoiceList();
            if (speechSynthesis.onvoiceschanged !== undefined) {
                speechSynthesis.onvoiceschanged = updateVoiceList;
            }
        }
    }

    /**
     * Speak current chapter
     */
    async function speakCurrentChapter() {
        if (!window.readerApp?.currentChapterText) return;

        // Clean text for speech
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = window.readerApp.currentChapterText;
        const plainText = tempDiv.textContent || tempDiv.innerText || '';

        if (!plainText.trim()) return;

        const speedSelector = document.getElementById('speed-selector');
        const rate = speedSelector ? parseFloat(speedSelector.value) : 1.0;

        const voiceSelect = document.getElementById('voice-select');
        const voiceValue = voiceSelect?.value;

        const engine = getCurrentEngineName();
        const tts = getTTS();
        if (!tts) return;

        if (engine === ENGINE_BROWSER) {
            // Browser TTS: get voice object from index
            const voiceIndex = parseInt(voiceValue) || 0;
            await tts.speak(plainText, {
                voice: webSpeechTTS?.getVoices()[voiceIndex],
                rate
            });
        } else {
            // Server TTS: pass voice ID directly
            await tts.speak(plainText, { voice: voiceValue, rate });
        }
    }

    /**
     * Update voice selection (restart with new voice if speaking)
     */
    async function updateVoice() {
        const tts = getTTS();
        if (!tts) return;

        const voiceSelect = document.getElementById('voice-select');
        const voiceValue = voiceSelect?.value;

        const engine = getCurrentEngineName();

        if (engine === ENGINE_BROWSER) {
            const voiceIndex = parseInt(voiceValue) || 0;
            if (webSpeechTTS?.getVoices()[voiceIndex]) {
                if (tts.isSpeaking()) {
                    const speedSelector = document.getElementById('speed-selector');
                    const rate = speedSelector ? parseFloat(speedSelector.value) : 1.0;
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = window.readerApp?.currentChapterText || '';
                    const plainText = tempDiv.textContent || tempDiv.innerText || '';

                    tts.speak(plainText, {
                        voice: webSpeechTTS.getVoices()[voiceIndex],
                        rate
                    });
                }
            }
        } else {
            if (tts.isSpeaking()) {
                tts.stop();
                await speakCurrentChapter();
            }
        }
    }

    /**
     * Update playback rate
     */
    function updateRate(rate) {
        localStorage.setItem('dawnstar_tts_rate', rate.toString());
        const rateDisplay = document.getElementById('rate-display');
        if (rateDisplay) {
            rateDisplay.textContent = parseFloat(rate).toFixed(1);
        }
    }

    /**
     * Toggle speech on/off
     */
    async function toggle() {
        const tts = getTTS();
        if (!tts) return;

        if (tts.isSpeaking() || isServerLoading) {
            tts.stop();
        } else {
            await speakCurrentChapter();
        }
    }

    /**
     * Pause/Resume toggle
     */
    function pauseResume() {
        const tts = getTTS();
        if (!tts) return;

        if (tts.isPaused) {
            tts.resume();
        } else if (tts.isSpeaking()) {
            tts.pause();
        }
    }

    // Web Speech API static check
    WebSpeechTTS.isSupported = function() {
        return 'speechSynthesis' in window;
    };

    /**
     * Keyboard shortcuts
     */
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            return;
        }

        if (e.key === 's' || e.key === 'S') {
            e.preventDefault();
            const tts = getTTS();
            if (tts && !tts.isSpeaking() && !isServerLoading) {
                speakCurrentChapter();
            }
        } else if (e.key === 'x' || e.key === 'X') {
            e.preventDefault();
            const tts = getTTS();
            if (tts) tts.stop();
        } else if (e.key === ' ') {
            e.preventDefault();
            pauseResume();
        } else if (e.key === '[') {
            e.preventDefault();
            const rateInput = document.getElementById('speed-selector');
            if (rateInput) {
                const newRate = Math.max(0.5, parseFloat(rateInput.value) - 0.1);
                rateInput.value = newRate.toFixed(1);
                updateRate(newRate);
            }
        } else if (e.key === ']') {
            e.preventDefault();
            const rateInput = document.getElementById('speed-selector');
            if (rateInput) {
                const newRate = Math.min(2.0, parseFloat(rateInput.value) + 0.1);
                rateInput.value = newRate.toFixed(1);
                updateRate(newRate);
            }
        }
    });

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTTS);
    } else {
        initTTS();
    }

    // ========================================
    // WORD HIGHLIGHTING
    // ========================================

    let _wordSpans = [];
    let _currentWordIndex = -1;
    let _isHighlighting = false;

    /**
     * Segment chapter text into word spans for highlighting.
     */
    function segmentWords() {
        const chapterText = document.getElementById('ic-chapter-text');
        if (!chapterText) return;

        // Clean up any previous spans
        clearHighlights();

        const walker = document.createTreeWalker(
            chapterText,
            NodeFilter.SHOW_TEXT,
            null
        );

        const textNodes = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.textContent.trim()) {
                textNodes.push(node);
            }
        }

        _wordSpans = [];
        let wordIndex = 0;
        const BATCH_SIZE = 50;
        let idx = 0;

        function processBatch() {
            const end = Math.min(idx + BATCH_SIZE, textNodes.length);
            for (; idx < end; idx++) {
                const textNode = textNodes[idx];
                const text = textNode.textContent;
                const words = text.split(/(\s+)/);

                if (words.length <= 1 && !text.trim()) continue;

                const parent = textNode.parentNode;
                if (!parent) continue;
                const fragment = document.createDocumentFragment();

                words.forEach(part => {
                    if (part.trim() === '') {
                        fragment.appendChild(document.createTextNode(part));
                    } else {
                        const span = document.createElement('span');
                        span.className = 'tts-word';
                        span.dataset.wordIndex = wordIndex;
                        span.textContent = part;
                        _wordSpans.push(span);
                        wordIndex++;
                        fragment.appendChild(span);
                    }
                });

                parent.replaceChild(fragment, textNode);
            }

            if (idx < textNodes.length) {
                requestAnimationFrame(processBatch);
            } else {
                _isHighlighting = true;
            }
        }

        if (textNodes.length === 0) return;
        requestAnimationFrame(processBatch);
    }

    /**
     * Highlight a specific word by index.
     */
    function highlightWord(index) {
        if (index < 0 || index >= _wordSpans.length) return;

        // Remove previous highlight
        if (_currentWordIndex >= 0 && _currentWordIndex < _wordSpans.length) {
            _wordSpans[_currentWordIndex].classList.remove('tts-word-highlight');
        }

        _currentWordIndex = index;
        _wordSpans[index].classList.add('tts-word-highlight');

        // Auto-scroll into view
        _wordSpans[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    /**
     * Clear all word highlights and restore original text.
     */
    function clearHighlights() {
        const chapterText = document.getElementById('ic-chapter-text');
        if (!chapterText) return;

        // Remove highlights
        chapterText.querySelectorAll('.tts-word-highlight').forEach(el => {
            el.classList.remove('tts-word-highlight');
        });

        _wordSpans = [];
        _currentWordIndex = -1;
        _isHighlighting = false;
    }

    /**
     * Start word tracking for browser TTS.
     */
    function startBrowserWordTracking(utterance) {
        segmentWords();
        let charCount = 0;
        const text = utterance.text;
        const words = text.split(/\s+/);

        utterance.onboundary = (event) => {
            if (event.name === 'word') {
                const charIndex = event.charIndex;
                // Count words up to this character index
                const textUpTo = text.substring(0, charIndex);
                const wordIndex = textUpTo.split(/\s+/).length - 1;
                if (wordIndex >= 0) {
                    highlightWord(wordIndex);
                }
            }
        };

        utterance.onend = () => {
            clearHighlights();
        };
    }

    /**
     * Start word tracking for server TTS using RAF timing estimation.
     */
    function startServerWordTracking() {
        segmentWords();
        if (_wordSpans.length === 0) return;

        const startTime = Date.now();
        const totalWords = _wordSpans.length;

        // Estimate ~150 words per minute at 1x speed
        const rate = parseFloat(document.getElementById('speed-selector')?.value || 1.0);
        const wordsPerMs = (150 * rate) / 60000;

        function trackWord() {
            if (!_isHighlighting) return;

            const elapsed = Date.now() - startTime;
            const currentIndex = Math.min(
                Math.floor(elapsed * wordsPerMs),
                totalWords - 1
            );

            if (currentIndex !== _currentWordIndex) {
                highlightWord(currentIndex);
            }

            if (currentIndex < totalWords - 1) {
                requestAnimationFrame(trackWord);
            } else {
                clearHighlights();
            }
        }

        requestAnimationFrame(trackWord);
    }

    // Export public API
    window.tts = {
        speak: (text, options) => getTTS()?.speak(text, options),
        pause: () => getTTS()?.pause(),
        resume: () => getTTS()?.resume(),
        stop: () => getTTS()?.stop(),
        toggle,
        pauseResume,
        isSpeaking: () => getTTS()?.isSpeaking() || false,
        segmentWords,
        highlightWord,
        clearHighlights,
        setRate: (rate) => getTTS()?.setRate(rate),
        speakCurrentChapter,
        getEngine: () => getCurrentEngineName(),
        setEngine: (engine) => {
            currentEngine = engine;
            localStorage.setItem('dawnstar_tts_engine', engine);
            getTTS()?.stop();
            updateVoiceList();
        },
        ENGINES: {
            EDGETTS: ENGINE_EDGETTS,
            BROWSER: ENGINE_BROWSER,
            GTTS: ENGINE_GTTS
        }
    };

    // Export global functions
    window.updateVoice = updateVoice;
    window.updateRate = updateRate;

})();
