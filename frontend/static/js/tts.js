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

                const response = await fetch('/api/tts/stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, voice, rate, pitch })
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || errorData.message || 'Failed to generate speech');
                }

                // Buffer all chunks, then play — avoids src-swap bugs
                const reader = response.body.getReader();
                const chunks = [];

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    chunks.push(value);
                }

                if (chunks.length === 0) {
                    throw new Error('No audio data received');
                }

                const objectUrl = URL.createObjectURL(new Blob(chunks, { type: 'audio/mpeg' }));

                audioElement = new Audio(objectUrl);
                audioElement.playbackRate = rate;
                audioElement.onended = () => this.stop();
                audioElement.onerror = (e) => {
                    console.error(`${this.engine} Audio Error:`, e);
                    this.stop();
                };
                audioElement.onplay = () => updateTTSButtonState('playing');
                audioElement.onpause = () => {
                    if (!this.isPaused) updateTTSButtonState('idle');
                };

                await audioElement.play();

                audioElement._objectUrl = objectUrl;
                // Single-segment highlight: wrap text as one segment
                _buildSegmentWordMap([text]);
                _buildSegmentSentenceMap();
                _startSegmentTracking(0);
                this.isPlaying = true;
                isServerLoading = false;

            } catch (error) {
                console.error(`${this.engine} TTS Error:`, error);
                isServerLoading = false;
                updateTTSButtonState('idle');
                throw error;
            }
        }

        /**
         * Speak text in segments — first segment plays immediately,
         * remaining segments are fetched while current one plays.
         */
        async speakSegments(segments, options = {}) {
            this.stop();
            if (segments.length === 0) return;

            const voice = options.voice || null;
            const rate = options.rate || 1.0;
            const pitch = options.pitch || '+0Hz';

            try {
                isServerLoading = true;
                updateTTSButtonState('loading');

                // Build segment-to-DOM-word mapping for highlighting
                _buildSegmentWordMap(segments);
                _buildSegmentSentenceMap();

                // Fetch first segment immediately
                const firstBlob = await _fetchAudioChunk(segments[0], voice, rate, pitch);

                const objectUrl = URL.createObjectURL(firstBlob);
                audioElement = new Audio(objectUrl);
                audioElement.playbackRate = rate;
                audioElement.onplay = () => updateTTSButtonState('playing');
                audioElement.onpause = () => {
                    if (!this.isPaused) updateTTSButtonState('idle');
                };

                this.isPlaying = true;
                isServerLoading = false;
                await audioElement.play();
                audioElement._objectUrl = objectUrl;

                // Start highlighting for segment 0
                _startSegmentTracking(0);

                // Prefetch next segment while current plays
                let prefetchPromise = segments.length > 1
                    ? _fetchAudioChunk(segments[1], voice, rate, pitch).catch(() => null)
                    : null;

                for (let i = 1; i < segments.length; i++) {
                    // Wait for current audio to end (unless stopped)
                    await new Promise((resolve) => {
                        if (!audioElement) { resolve(); return; }
                        audioElement.onended = () => resolve();
                        const checkStop = setInterval(() => {
                            if (!this.isPlaying) { clearInterval(checkStop); resolve(); }
                        }, 200);
                    });

                    if (!this.isPlaying) break;

                    // Use prefetched blob or fetch now
                    const blob = await prefetchPromise ||
                        await _fetchAudioChunk(segments[i], voice, rate, pitch).catch(() => null);
                    if (!blob) break;

                    // Start prefetching next segment
                    prefetchPromise = (i + 1 < segments.length)
                        ? _fetchAudioChunk(segments[i + 1], voice, rate, pitch).catch(() => null)
                        : null;

                    const newUrl = URL.createObjectURL(blob);
                    if (audioElement._objectUrl) URL.revokeObjectURL(audioElement._objectUrl);
                    audioElement.src = newUrl;
                    audioElement._objectUrl = newUrl;
                    await audioElement.play();

                    _startSegmentTracking(i);
                }

                // Final segment ended
                audioElement.onended = () => this.stop();

            } catch (error) {
                console.error(`${this.engine} Segment TTS Error:`, error);
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
                if (audioElement._objectUrl) {
                    URL.revokeObjectURL(audioElement._objectUrl);
                }
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
        if (btn) {
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

        // Notify reader-specific UI (e.g. reader-icecream.js) of state change
        if (typeof window.updateTTSUI === 'function') {
            window.updateTTSUI(state);
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
     * Speak current chapter — splits into sentence chunks for fast first-byte.
     */
    async function speakCurrentChapter() {
        const chapterTextEl = document.getElementById('ic-chapter-text');
        if (!chapterTextEl) return;

        const text = chapterTextEl.innerText || chapterTextEl.textContent;
        if (!text || !text.trim()) return;

        const plainText = text.replace(/\s+/g, ' ').trim();

        const rate = parseFloat(localStorage.getItem('dawnstar_tts_rate') || '1.0');
        const voiceValue = localStorage.getItem('dawnstar_tts_voice_' + (getCurrentEngineName() || currentEngine));

        const engine = getCurrentEngineName();
        const tts = getTTS();
        if (!tts) return;

        if (engine === ENGINE_BROWSER) {
            const voiceIndex = parseInt(voiceValue) || 0;
            await tts.speak(plainText, {
                voice: webSpeechTTS?.getVoices()[voiceIndex],
                rate
            });
        } else {
            // Server TTS: split into ~500-char segments so first chunk plays fast
            const MAX_CHUNK = 500;
            const segments = splitTextIntoSegments(plainText, MAX_CHUNK);
            await tts.speakSegments(segments, { voice: voiceValue, rate });
        }
    }

    /**
     * Split text into sentence-boundary chunks of roughly maxLen characters.
     */
    function splitTextIntoSegments(text, maxLen) {
        const segments = [];
        // Split on sentence boundaries
        const sentences = text.match(/[^.!?]+[.!?]+[\s]*/g) || [text];
        let current = '';

        for (const sentence of sentences) {
            if ((current + sentence).length > maxLen && current.length > 0) {
                segments.push(current.trim());
                current = sentence;
            } else {
                current += sentence;
            }
        }
        if (current.trim()) segments.push(current.trim());
        return segments.length > 0 ? segments : [text];
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
    // SENTENCE HIGHLIGHTING (segment-aware)
    // ========================================

    let _wordSpans = [];         // All word spans in the chapter DOM
    let _currentWordIndex = -1;  // Currently highlighted word
    let _isHighlighting = false;
    let _segmentWordMap = [];    // [{startWord, endWord}, ...] per segment
    let _trackRAF = null;        // RAF handle for tracking loop
    let _sentenceSpans = [];     // All sentence spans in the chapter DOM
    let _currentSentenceIndex = -1; // Currently highlighted sentence
    let _segmentSentenceMap = []; // [{startSentence, endSentence}, ...] per segment

    /**
     * Wrap sentences and words in the chapter DOM with spans.
     * First wraps sentences, then wraps words inside each sentence.
     */
    function segmentSentencesAndWords() {
        const chapterText = document.getElementById('ic-chapter-text');
        if (!chapterText) { console.warn('[TTS] #ic-chapter-text not found'); return; }

        // Unwrap any previous tts-sentence and tts-word spans
        chapterText.querySelectorAll('span.tts-sentence, span.tts-word').forEach(span => {
            const parent = span.parentNode;
            if (parent) {
                // Replace with text content
                while (span.firstChild) {
                    parent.insertBefore(span.firstChild, span);
                }
                span.remove();
            }
        });
        chapterText.normalize();

        const walker = document.createTreeWalker(chapterText, NodeFilter.SHOW_TEXT, null);
        const textNodes = [];
        let node;
        while ((node = walker.nextNode())) {
            if (node.textContent.trim()) textNodes.push(node);
        }

        _sentenceSpans = [];
        _wordSpans = [];
        let sentenceIndex = 0;
        let wordIndex = 0;

        // Sentence boundary regex: split on . ! ? followed by space or end
        const sentenceRegex = /([.!?]+\s*)/g;

        for (const textNode of textNodes) {
            const text = textNode.textContent;
            const parts = text.split(sentenceRegex);

            const parent = textNode.parentNode;
            if (!parent) continue;
            const fragment = document.createDocumentFragment();

            let currentSentence = '';
            for (let i = 0; i < parts.length; i++) {
                const part = parts[i];
                if (part.trim() === '') continue;

                currentSentence += part;

                // Check if this part ends with sentence boundary (. ! ?)
                if (/[.!?]$/.test(part.trim())) {
                    const trimmed = currentSentence.trim();
                    if (trimmed) {
                        // Create sentence span
                        const sentenceSpan = document.createElement('span');
                        sentenceSpan.className = 'tts-sentence';
                        sentenceSpan.dataset.sentenceIndex = sentenceIndex;

                        // Now split this sentence into words
                        const words = currentSentence.split(/(\s+)/);
                        for (const wordPart of words) {
                            if (wordPart.trim() === '') {
                                sentenceSpan.appendChild(document.createTextNode(wordPart));
                            } else {
                                const wordSpan = document.createElement('span');
                                wordSpan.className = 'tts-word';
                                wordSpan.dataset.wordIndex = wordIndex;
                                wordSpan.textContent = wordPart;
                                _wordSpans.push(wordSpan);
                                wordIndex++;
                                sentenceSpan.appendChild(wordSpan);
                            }
                        }

                        _sentenceSpans.push(sentenceSpan);
                        sentenceIndex++;
                        fragment.appendChild(sentenceSpan);
                        currentSentence = '';
                    }
                }
            }
            // Handle any remaining text without sentence boundary
            if (currentSentence.trim()) {
                const sentenceSpan = document.createElement('span');
                sentenceSpan.className = 'tts-sentence';
                sentenceSpan.dataset.sentenceIndex = sentenceIndex;

                // Split into words
                const words = currentSentence.split(/(\s+)/);
                for (const wordPart of words) {
                    if (wordPart.trim() === '') {
                        sentenceSpan.appendChild(document.createTextNode(wordPart));
                    } else {
                        const wordSpan = document.createElement('span');
                        wordSpan.className = 'tts-word';
                        wordSpan.dataset.wordIndex = wordIndex;
                        wordSpan.textContent = wordPart;
                        _wordSpans.push(wordSpan);
                        wordIndex++;
                        sentenceSpan.appendChild(wordSpan);
                    }
                }

                _sentenceSpans.push(sentenceSpan);
                sentenceIndex++;
                fragment.appendChild(sentenceSpan);
            }
            parent.replaceChild(fragment, textNode);
        }
    }

    /**
     * Build a map from TTS segment index → DOM word range.
     */
    function _buildSegmentWordMap(segments) {
        segmentSentencesAndWords();

        const allWords = _wordSpans.map(s => s.textContent.trim());
        _segmentWordMap = [];

        let searchStart = 0;
        for (const seg of segments) {
            const segWords = seg.split(/\s+/).filter(w => w.length > 0);
            if (segWords.length === 0) {
                _segmentWordMap.push({ startWord: searchStart, endWord: searchStart });
                continue;
            }

            let found = false;
            for (let i = searchStart; i <= allWords.length - segWords.length; i++) {
                let match = true;
                for (let j = 0; j < Math.min(segWords.length, 5); j++) {
                    if (allWords[i + j].toLowerCase() !== segWords[j].toLowerCase()) {
                        match = false;
                        break;
                    }
                }
                if (match) {
                    const endWord = Math.min(i + segWords.length, allWords.length);
                    _segmentWordMap.push({ startWord: i, endWord: endWord });
                    searchStart = endWord;
                    found = true;
                    break;
                }
            }

            if (!found) {
                const startWord = searchStart;
                const endWord = Math.min(searchStart + segWords.length, allWords.length);
                _segmentWordMap.push({ startWord, endWord });
                searchStart = endWord;
            }
        }
        _isHighlighting = _wordSpans.length > 0;
    }

    /**
     * Build a map from TTS segment index → DOM sentence range.
     * Uses text matching to find which sentences contain the segment's words.
     */
    function _buildSegmentSentenceMap() {
        // segmentSentencesAndWords is already called by _buildSegmentWordMap
        if (_wordSpans.length === 0 || _sentenceSpans.length === 0) {
            _segmentSentenceMap = [];
            return;
        }

        // Build word index for each sentence
        const sentenceWordRanges = [];
        let wordIndex = 0;

        for (const sentence of _sentenceSpans) {
            const sentenceWords = sentence.textContent.trim().split(/\s+/).filter(w => w.length > 0).length;
            sentenceWordRanges.push({ start: wordIndex, end: wordIndex + sentenceWords });
            wordIndex += sentenceWords;
        }

        // Map each segment to its sentence range
        _segmentSentenceMap = _segmentWordMap.map(range => {
            if (range.startWord >= range.endWord) {
                return { startSentence: 0, endSentence: 1 };
            }

            // Find which sentence contains the start word
            let startSentence = 0;
            for (let s = 0; s < sentenceWordRanges.length; s++) {
                if (range.startWord >= sentenceWordRanges[s].start && range.startWord < sentenceWordRanges[s].end) {
                    startSentence = s;
                    break;
                }
            }

            // Find which sentence contains the end word
            let endSentence = startSentence + 1;
            for (let s = 0; s < sentenceWordRanges.length; s++) {
                if (range.endWord > sentenceWordRanges[s].start && range.endWord <= sentenceWordRanges[s].end) {
                    endSentence = s + 1;
                    break;
                }
            }

            return { startSentence, endSentence };
        });
    }

    /**
     * Highlight the sentence for the current segment.
     */
    function _highlightSentence(segIndex) {
        // Clear previous sentence highlight
        if (_currentSentenceIndex >= 0 && _currentSentenceIndex < _sentenceSpans.length) {
            _sentenceSpans[_currentSentenceIndex].classList.remove('tts-sentence-highlight');
        }

        const sentenceRange = _segmentSentenceMap[segIndex];
        if (!sentenceRange || sentenceRange.startSentence >= sentenceRange.endSentence) {
            return;
        }

        // Highlight the first sentence in the range (most segments contain one sentence)
        _currentSentenceIndex = sentenceRange.startSentence;
        if (_currentSentenceIndex < _sentenceSpans.length) {
            _sentenceSpans[_currentSentenceIndex].classList.add('tts-sentence-highlight');
        }
    }

    /**
     * Start timeupdate-based word tracking for a given segment index.
     * Uses actual audio duration for precise sync.
     */
    function _startSegmentTracking(segIndex) {
        if (_trackRAF) cancelAnimationFrame(_trackRAF);

        const range = _segmentWordMap[segIndex];
        if (!range || range.startWord >= range.endWord) {
            console.warn('[TTS] No range for segment', segIndex, range);
            return;
        }

        const totalSegWords = range.endWord - range.startWord;
        _dimSegmentWords(segIndex);
        _highlightSentence(segIndex);

        // Estimate speech rate: ~150 WPM at 1x, scaled by playback rate
        const rate = parseFloat(document.getElementById('speed-selector')?.value || 1.0) || 1.0;
        const wordsPerSec = (150 * rate) / 60;
        const startTime = performance.now();
        let loggedOnce = false;

        function tick() {
            if (!audioElement || !_isHighlighting) {
                if (!loggedOnce) console.warn('[TTS] tick exit: audio=', !!audioElement, 'highlighting=', _isHighlighting);
                return;
            }

            let progress;
            if (audioElement.duration && isFinite(audioElement.duration)) {
                progress = Math.min(audioElement.currentTime / audioElement.duration, 1);
            } else {
                const elapsedSec = (performance.now() - startTime) / 1000;
                const estDuration = totalSegWords / wordsPerSec;
                progress = Math.min(elapsedSec / estDuration, 1);
            }

            const wordOffset = Math.min(Math.floor(progress * totalSegWords), totalSegWords - 1);
            const wordIndex = range.startWord + wordOffset;

            if (wordIndex !== _currentWordIndex && wordIndex < _wordSpans.length) {
                if (_currentWordIndex >= 0 && _currentWordIndex < _wordSpans.length) {
                    _wordSpans[_currentWordIndex].classList.remove('tts-word-highlight');
                }
                _currentWordIndex = wordIndex;
                _wordSpans[wordIndex].classList.add('tts-word-highlight');
                _wordSpans[wordIndex].scrollIntoView({ behavior: 'smooth', block: 'center' });
            }

            if (segIndex < _segmentWordMap.length - 1 || progress < 0.99) {
                _trackRAF = requestAnimationFrame(tick);
            }
        }

        _trackRAF = requestAnimationFrame(tick);
    }

    /**
     * Dim words from previous segments, keep current segment normal.
     */
    function _dimSegmentWords(currentSegIndex) {
        for (let i = 0; i < _segmentWordMap.length; i++) {
            const range = _segmentWordMap[i];
            for (let w = range.startWord; w < range.endWord; w++) {
                if (w < _wordSpans.length) {
                    if (i < currentSegIndex) {
                        _wordSpans[w].classList.add('tts-word-spoken');
                        _wordSpans[w].classList.remove('tts-word-highlight');
                    } else {
                        _wordSpans[w].classList.remove('tts-word-spoken');
                    }
                }
            }
        }
    }

    function highlightWord(index) {
        if (index < 0 || index >= _wordSpans.length) return;
        if (_currentWordIndex >= 0 && _currentWordIndex < _wordSpans.length) {
            _wordSpans[_currentWordIndex].classList.remove('tts-word-highlight');
        }
        _currentWordIndex = index;
        _wordSpans[index].classList.add('tts-word-highlight');
        _wordSpans[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    function clearHighlights() {
        const chapterText = document.getElementById('ic-chapter-text');
        if (!chapterText) return;
        chapterText.querySelectorAll('.tts-word-highlight, .tts-word-spoken').forEach(el => {
            el.classList.remove('tts-word-highlight', 'tts-word-spoken');
        });
        chapterText.querySelectorAll('.tts-sentence-highlight').forEach(el => {
            el.classList.remove('tts-sentence-highlight');
        });
        _wordSpans = [];
        _sentenceSpans = [];
        _currentWordIndex = -1;
        _currentSentenceIndex = -1;
        _isHighlighting = false;
        _segmentWordMap = [];
        _segmentSentenceMap = [];
        if (_trackRAF) cancelAnimationFrame(_trackRAF);
        _trackRAF = null;
    }

    /**
     * Start word tracking for browser TTS.
     */
    function startBrowserWordTracking(utterance) {
        segmentSentencesAndWords();
        const text = utterance.text;

        utterance.onboundary = (event) => {
            if (event.name === 'word') {
                const textUpTo = text.substring(0, event.charIndex);
                const wordIndex = textUpTo.split(/\s+/).length - 1;
                if (wordIndex >= 0) highlightWord(wordIndex);
            }
        };
        utterance.onend = () => clearHighlights();
    }

    /**
     * Fetch a single audio chunk from the server and return as Blob.
     */
    async function _fetchAudioChunk(text, voice, rate, pitch) {
        const response = await fetch('/api/tts/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, voice, rate, pitch })
        });
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || 'TTS chunk failed');
        }
        const reader = response.body.getReader();
        const chunks = [];
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            chunks.push(value);
        }
        if (chunks.length === 0) throw new Error('Empty audio response');
        return new Blob(chunks, { type: 'audio/mpeg' });
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
        isLoading: () => isServerLoading,
        segmentSentencesAndWords,
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
        getRate: () => parseFloat(localStorage.getItem('dawnstar_tts_rate') || '1.0'),
        setVolume: (volume) => {
            if (audioElement) {
                audioElement.volume = Math.max(0, Math.min(1, volume / 100));
            }
        },
        getVoices: () => {
            const engine = getCurrentEngineName();
            if (engine === ENGINE_EDGETTS) return edgeTTSVoices;
            if (engine === ENGINE_GTTS) return gttsVoices;
            return webSpeechTTS?.getVoices() || [];
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
