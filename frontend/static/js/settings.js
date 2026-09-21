// Settings Page JavaScript for eBook Manager

/* global apiGet, apiPost, apiFetch, ApiError */

// Current active tab

/**
 * Human-readable message from an ApiError — some endpoints send `detail`
 * as an object ({error, message}) rather than a plain string.
 * @param {Error} error
 * @returns {string}
 */
function apiErrorMessage(error) {
  const detail = error instanceof ApiError ? error.body?.detail : null;
  if (Array.isArray(detail)) {
    // FastAPI validation errors arrive as [{loc, msg, type}, ...]
    return detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
  }
  if (detail && typeof detail === "object") {
    return detail.message || detail.error || JSON.stringify(detail);
  }
  return error.message;
}

/**
 * Initialize settings page
 */
document.addEventListener("DOMContentLoaded", () => {
  // Load saved settings
  loadSettings();

  // Initialize TTS voices
  loadVoices();

  // Initialize theme selection
  initializeThemeSelection();

  // Apply active class to first nav item
  document.querySelector(".settings-nav-item").classList.add("active");
});

/**
 * Switch between settings tabs
 */
function switchTab(tabId) {

  // Update nav items
  document.querySelectorAll(".settings-nav-item").forEach((item) => {
    item.classList.remove("active");
    if (item.dataset.tab === tabId) {
      item.classList.add("active");
    }
  });

  // Update panels
  document.querySelectorAll(".settings-panel").forEach((panel) => {
    panel.classList.remove("active");
  });
  document.getElementById(`panel-${tabId}`).classList.add("active");
}

/**
 * Load settings from localStorage and server
 */
async function loadSettings() {
  // Server is source of truth — load from API first
  try {
    const serverSettings = await apiGet("/api/settings");
    applySettingsToUI(serverSettings);
    return;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      window.location.href = "/login";
      return;
    }
    console.error("Failed to load settings from server:", error);
    showNotification(
      "Could not load settings from the server. Showing saved values.",
      "error",
    );
  }

  // Fallback: load from localStorage if server unavailable
  const savedSettings = JSON.parse(
    localStorage.getItem("dawnstar-settings") || "{}",
  );
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
    library_path: "library-path",
    auto_scan: "auto-scan",
    watch_changes: "watch-changes",
    page_layout: "page-layout",
    text_align: "text-align",
    font_size: "font-size",
    font_family: "font-family",
    line_height: "line-height",
    theme: "theme",
    tts_speed: "tts-speed",
    tts_pitch: "tts-pitch",
    ai_provider: "ai-provider",
    ollama_url: "ollama-url",
    auto_flip: "auto-flip",
    flip_interval: "flip-interval",
    summary_length: "summary-length",
    auto_summary: "auto-summary",
    nas_enabled: "nas-enabled",
    nas_host: "nas-host",
    nas_share: "nas-share",
    nas_mount_path: "nas-mount-path",
    nas_protocol: "nas-protocol",
    nas_username: "nas-username",
    nas_auto_mount: "nas-auto-mount",
    calibre_web_url: "calibre-web-url",
  };

  Object.entries(keyToId).forEach(([key, elemId]) => {
    if (settings[key] === undefined) return;
    const element = document.getElementById(elemId);
    if (!element) return;

    if (element.type === "checkbox") {
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
    library_path: document.getElementById("library-path").value,
    auto_scan: document.getElementById("auto-scan").checked,
    watch_changes: document.getElementById("watch-changes").checked,
    page_layout: document.getElementById("page-layout").value,
    text_align: document.getElementById("text-align").value,
    font_size: parseInt(document.getElementById("font-size").value),
    font_family: document.getElementById("font-family").value,
    line_height: document.getElementById("line-height").value,
    theme:
      document.querySelector(".theme-option.selected")?.dataset.theme || "day",
    tts_speed: document.getElementById("tts-speed").value,
    tts_pitch: parseFloat(document.getElementById("tts-pitch").value),
    ai_provider: document.getElementById("ai-provider").value,
    ai_api_key: document.getElementById("ai-api-key").value,
    ollama_url: document.getElementById("ollama-url").value,
    auto_flip: document.getElementById("auto-flip").checked,
    flip_interval: parseInt(document.getElementById("flip-interval").value),
    summary_length: document.getElementById("summary-length").value,
    auto_summary: document.getElementById("auto-summary").checked,
    // NAS settings
    nas_enabled: document.getElementById("nas-enabled").checked,
    nas_host: document.getElementById("nas-host").value,
    nas_share: document.getElementById("nas-share").value,
    nas_mount_path: document.getElementById("nas-mount-path").value,
    nas_protocol: document.getElementById("nas-protocol").value,
    nas_username: document.getElementById("nas-username").value,
    nas_password: document.getElementById("nas-password").value,
    nas_auto_mount: false,
    calibre_web_url: document.getElementById("calibre-web-url")?.value || "",
  };

  // Save to localStorage
  localStorage.setItem("dawnstar-settings", JSON.stringify(settings));

  // Also save individual settings for use in other pages
  localStorage.setItem("reader-theme", settings.theme);
  localStorage.setItem("reader-zoom", settings.font_size.toString());

  // Save to server
  try {
    await apiPost("/api/settings", settings);
    showNotification("Settings saved successfully!", "success");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      // Session expired — redirect to login
      showNotification("Session expired. Redirecting to login...", "warning");
      setTimeout(() => {
        window.location.href = "/login";
      }, 1500);
      return;
    }
    console.error("Failed to save settings:", error);
    showNotification(
      "Settings saved locally. Could not sync with server: " +
        apiErrorMessage(error),
      "warning",
    );
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
    button.classList.add("loading");
    button.disabled = true;
    const originalText = button.textContent;
    button.dataset.originalText = originalText;
    button.innerHTML =
      '<span class="btn-text" style="visibility: hidden;">' +
      originalText +
      "</span>";
  } else {
    button.classList.remove("loading");
    button.disabled = false;
    const originalText = button.dataset.originalText || "Save Settings";
    button.textContent = originalText;
    delete button.dataset.originalText;
  }
}

/**
 * Reset settings to defaults
 */
function resetSettings() {
  if (!confirm("Are you sure you want to reset all settings to defaults?")) {
    return;
  }

  localStorage.removeItem("dawnstar-settings");

  // Reset form elements to defaults
  document.getElementById("library-path").value = "/home/user/ebooks";
  document.getElementById("auto-scan").checked = false;
  document.getElementById("watch-changes").checked = false;
  document.getElementById("page-layout").value = "single";
  document.getElementById("text-align").value = "justify";
  document.getElementById("font-size").value = 100;
  document.getElementById("font-family").value = "georgia";
  document.getElementById("line-height").value = "1.8";
  document.getElementById("tts-speed").value = "1.0";
  document.getElementById("tts-pitch").value = 1;
  document.getElementById("auto-flip").checked = false;
  document.getElementById("flip-interval").value = 30;

  updateFontSizeDisplay(100);
  updatePitchDisplay(1);
  selectTheme("day");

  showNotification("Settings reset to defaults", "info");
}

/**
 * Reset hotkeys to defaults
 */
function resetHotkeys() {
  if (!confirm("Reset all keyboard shortcuts to defaults?")) {
    return;
  }
  showNotification("Hotkeys reset to defaults", "info");
}

/**
 * Load available TTS voices
 */
async function loadVoices() {
  const engineSelect = document.getElementById("tts-engine");
  const savedEngine = localStorage.getItem("tts-engine") || "edgetts";
  engineSelect.value = savedEngine;
  const currentEngine = engineSelect.value || "edgetts";

  if (currentEngine === "gtts") {
    await loadGTVoices();
  } else if (currentEngine === "edgetts") {
    await loadEdgeVoices();
  } else {
    loadWebSpeechVoices();
  }
}

/**
 * Load Web Speech API voices (browser TTS)
 */
function loadWebSpeechVoices() {
  const voiceSelect = document.getElementById("tts-voice");

  const populateVoices = () => {
    const voices = speechSynthesis.getVoices();
    voiceSelect.innerHTML = '<option value="">Select a voice...</option>';

    // Group voices by language
    const voicesByLang = {};
    voices.forEach((voice) => {
      const lang = voice.lang.split("-")[0];
      if (!voicesByLang[lang]) voicesByLang[lang] = [];
      voicesByLang[lang].push(voice);
    });

    // Sort languages alphabetically
    Object.keys(voicesByLang)
      .sort()
      .forEach((lang) => {
        const optgroup = document.createElement("optgroup");
        optgroup.label = lang.toUpperCase();
        voicesByLang[lang].forEach((voice) => {
          const option = document.createElement("option");
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
  const voiceSelect = document.getElementById("tts-voice");
  voiceSelect.innerHTML = '<option value="">Loading voices...</option>';

  try {
    const data = await apiGet("/api/tts/voices?engine=edgetts");
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
    Object.keys(voicesByLocale)
      .sort()
      .forEach((locale) => {
        const optgroup = document.createElement("optgroup");
        optgroup.label = locale.toUpperCase();
        voicesByLocale[locale].forEach((voice) => {
          const option = document.createElement("option");
          option.value = `edgetts:${voice.id}`;
          option.textContent = voice.name;
          if (voice.id === data.default_voice) {
            option.selected = true;
          }
          optgroup.appendChild(option);
        });
        voiceSelect.appendChild(optgroup);
      });

    // Restore the operator's saved voice: this browser's local choice first,
    // then the server-side default (another browser/origin), then EdgeTTS default
    let savedVoice = localStorage.getItem("dawnstar_tts_voice_edgetts") || "";
    if (!savedVoice) {
      try {
        const settings = await apiGet("/api/settings");
        const serverVoice = (settings.tts_voice || "").replace(/^\w+:/, "");
        if (settings.tts_engine) localStorage.setItem("dawnstar_tts_engine", settings.tts_engine);
        if (serverVoice) {
          localStorage.setItem("dawnstar_tts_voice_edgetts", serverVoice);
          savedVoice = serverVoice;
        }
      } catch (error) {
        console.warn("Voice default lookup skipped:", error);
      }
    }
    if (savedVoice && voiceSelect.querySelector(`option[value="edgetts:${savedVoice}"]`)) {
      voiceSelect.value = `edgetts:${savedVoice}`;
    }
  } catch (error) {
    console.error("Failed to load EdgeTTS voices:", error);
    voiceSelect.innerHTML = '<option value="">Failed to load voices</option>';
    showNotification(`Could not load EdgeTTS voices: ${error.message}`, "error");
  }
}

/**
 * Load gTTS voices/languages from server
 */
async function loadGTVoices() {
  const voiceSelect = document.getElementById("tts-voice");
  voiceSelect.innerHTML = '<option value="">Loading voices...</option>';

  try {
    const data = await apiGet("/api/tts/voices?engine=gtts");
    const voices = data.voices || [];

    voiceSelect.innerHTML = '<option value="">Select a language...</option>';

    // Group voices by locale
    const voicesByLocale = {};
    voices.forEach((voice) => {
      const locale = voice.Locale.split("-")[0];
      if (!voicesByLocale[locale]) voicesByLocale[locale] = [];
      voicesByLocale[locale].push(voice);
    });

    // Sort locales alphabetically
    Object.keys(voicesByLocale)
      .sort()
      .forEach((locale) => {
        const optgroup = document.createElement("optgroup");
        optgroup.label = locale.toUpperCase();
        voicesByLocale[locale].forEach((voice) => {
          const option = document.createElement("option");
          option.value = `gtts:${voice.ShortName}`;
          option.textContent = voice.FriendlyName;
          if (voice.ShortName === data.default_voice) {
            option.selected = true;
          }
          optgroup.appendChild(option);
        });
        voiceSelect.appendChild(optgroup);
      });

    const savedGTVoice = localStorage.getItem("dawnstar_tts_voice_gtts") || "";
    if (savedGTVoice && voiceSelect.querySelector(`option[value="gtts:${savedGTVoice}"]`)) {
      voiceSelect.value = `gtts:${savedGTVoice}`;
    }
  } catch (error) {
    console.error("Failed to load gTTS voices:", error);
    voiceSelect.innerHTML = '<option value="">Failed to load voices</option>';
    showNotification(`Could not load gTTS voices: ${error.message}`, "error");
  }
}

/**
 * Change TTS engine
 */
function changeTTSEngine(engine) {
  localStorage.setItem("tts-engine", engine);
  // The reader's TTS engine reads dawnstar_tts_engine — keep both keys in sync
  localStorage.setItem("dawnstar_tts_engine", engine);
  loadVoices();

  // Show/hide pitch control (only for Web Speech and EdgeTTS)
  const pitchRow = document
    .getElementById("tts-pitch")
    ?.closest(".setting-row");
  if (pitchRow) {
    pitchRow.style.display = engine === "gtts" ? "none" : "flex";
  }
}

/**
 * Persist the selected voice to the keys the reader's speak path consumes
 * (dawnstar_tts_voice_<engine> / dawnstar_tts_engine). Without this the
 * chosen voice never reaches synthesis — the reader had no other writer.
 * Option values are engine-prefixed: "edgetts:en-US-GuyNeural".
 */
function onTTSVoiceChanged() {
  const value = document.getElementById("tts-voice")?.value || "";
  const sep = value.indexOf(":");
  const prefix = sep === -1 ? "" : value.slice(0, sep);
  const voiceId = sep === -1 ? value : value.slice(sep + 1);
  if (!voiceId) return;
  // tts.js calls the Web Speech engine "browser"; settings options say "webspeech"
  const engine = prefix === "webspeech" ? "browser" : prefix || localStorage.getItem("tts-engine") || "edgetts";
  localStorage.setItem(`dawnstar_tts_voice_${engine}`, voiceId);
  if (prefix) localStorage.setItem("dawnstar_tts_engine", engine);

  // Persist server-side IMMEDIATELY (not only on Save) — localStorage is
  // per-origin, so a voice picked on localhost must follow the operator to
  // the LAN address, another browser, and the packaged service.
  const full = prefix ? value : `${engine}:${voiceId}`;
  apiPost("/api/settings", { tts_engine: engine, tts_voice: full }).catch((error) => {
    showNotification(`Could not save default voice: ${apiErrorMessage(error)}`, "error");
  });
}

/**
 * Test TTS with current settings
 */
async function testTTS() {
  const engine = document.getElementById("tts-engine").value;
  const voice = document.getElementById("tts-voice").value;
  const speed = document.getElementById("tts-speed").value;
  const pitch = document.getElementById("tts-pitch").value;

  const testText =
    "This is a test of the text to speech feature. You should be hearing this in the language you selected.";

  if (engine === "gtts" || engine === "edgetts") {
    // Test with server-side TTS
    try {
      const voiceId = voice.replace(`${engine}:`, "");
      const engineName = engine === "edgetts" ? "edgetts" : "gtts";

      // apiFetch (not apiPost): the response is an audio blob, not JSON.
      const response = await apiFetch("/api/tts/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: testText,
          voice: voiceId,
          rate: speed,
          pitch: "+0Hz",
          engine: engineName,
        }),
      });

      if (!response.ok) throw new Error("TTS synthesis failed");

      const audioBlob = await response.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      await audio.play();

      // Check which engine actually generated the audio
      const actualEngine = response.headers.get("X-TTS-Engine");
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

    if (voice && voice !== "default") {
      const voices = speechSynthesis.getVoices();
      const voiceIndex = parseInt(voice.replace("webspeech:", ""));
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
  // reader-theme wins; fall back to the app-wide theme so night users aren't
  // flashed back to day on this page before the API responds.
  const savedTheme =
    localStorage.getItem("reader-theme") ||
    localStorage.getItem("dawnstar_theme") ||
    "day";
  selectTheme(savedTheme);
}

/**
 * Select a theme
 */
function selectTheme(theme) {
  // Swatch highlight only: the page chrome follows dawnstar_theme (pre-paint
  // inline script + theme.js). Applying the reader theme here would flip the
  // shell after paint whenever the two themes differ.
  document.querySelectorAll(".theme-option").forEach((option) => {
    option.classList.remove("selected");
    if (option.dataset.theme === theme) {
      option.classList.add("selected");
    }
  });
}

/**
 * Update font size display
 */
function updateFontSizeDisplay(value) {
  document.getElementById("font-size-display").textContent = `${value}%`;
}

/**
 * Update pitch display
 */
function updatePitchDisplay(value) {
  document.getElementById("pitch-display").textContent =
    parseFloat(value).toFixed(1);
}

/**
 * Update AI provider settings visibility
 */
function updateAIProviderSettings() {
  const provider = document.getElementById("ai-provider").value;
  const ollamaRow = document.getElementById("ollama-url-row");

  if (provider === "ollama") {
    ollamaRow.style.display = "flex";
  } else {
    ollamaRow.style.display = "none";
  }
}

/**
 * Browse for library path
 */
function browseLibraryPath() {
  showNotification(
    "Please enter the path manually. Path browsing is not available in web interface.",
    "info",
  );
  document.getElementById("library-path").focus();
}

/**
 * Test AI connection
 */
async function testAIConnection(event) {
  const provider = document.getElementById("ai-provider").value;
  const apiKey = document.getElementById("ai-api-key").value;

  if (!apiKey && provider !== "ollama") {
    showNotification("Please enter an API key first", "warning");
    return;
  }

  const btn = event.target;
  setButtonLoading(btn, true);

  try {
    const result = await apiPost("/api/settings/test-ai", {
      provider,
      api_key: apiKey,
    });
    showNotification(
      `AI connection successful! Provider: ${result.provider}`,
      "success",
    );
  } catch (error) {
    showNotification(`Connection failed: ${apiErrorMessage(error)}`, "error");
  } finally {
    setButtonLoading(btn, false);
  }
}

/**
 * Test NAS connection
 */
async function testNASConnection(event) {
  const btn = event.target;
  setButtonLoading(btn, true);

  const statusDiv = document.getElementById("nas-status");
  const statusDot = document.getElementById("nas-status-dot");
  const statusText = document.getElementById("nas-status-text");

  try {
    // First save NAS settings so the test endpoint can use them
    const nasSettings = {
      nas_enabled: document.getElementById("nas-enabled").checked,
      nas_host: document.getElementById("nas-host").value,
      nas_share: document.getElementById("nas-share").value,
      nas_mount_path: document.getElementById("nas-mount-path").value,
      nas_protocol: document.getElementById("nas-protocol").value,
      nas_username: document.getElementById("nas-username").value,
      nas_password: document.getElementById("nas-password").value,
    };

    // Save settings first, then test the connection with them
    await apiPost("/api/settings", nasSettings);
    const result = await apiPost("/api/settings/test-nas");

    statusDiv.style.display = "block";
    statusDot.style.backgroundColor = "#4CAF50";
    statusText.textContent = result.message;
    showNotification("NAS connection successful!", "success");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      showNotification("Session expired. Redirecting to login...", "warning");
      setTimeout(() => {
        window.location.href = "/login";
      }, 1500);
      return;
    }
    statusDiv.style.display = "block";
    statusDot.style.backgroundColor = "#f44336";
    statusText.textContent = apiErrorMessage(error);
    showNotification(`NAS connection failed: ${apiErrorMessage(error)}`, "error");
  } finally {
    setButtonLoading(btn, false);
  }
}

/* Calibre integration ---------------------------------------------- */

/**
 * Pre-flight check that a path is a valid Calibre library before importing.
 * Calls GET /api/library/calibre-status and shows the volume count.
 */
async function calibreCheckStatus(event) {
  if (event) event.preventDefault();
  const input = document.getElementById("calibre-library-path");
  const statusBox = document.getElementById("calibre-status");
  const statusText = document.getElementById("calibre-status-text");
  if (!input || !input.value.trim()) {
    showNotification("Enter a Calibre library path first", "warning");
    return;
  }
  statusBox.style.display = "block";
  statusText.textContent = "Checking...";
  try {
    const url =
      "/api/library/calibre-status?path=" +
      encodeURIComponent(input.value.trim());
    const data = await apiGet(url);
    if (data.valid) {
      statusText.innerHTML = `<span style="color:#4CAF50;font-weight:600;">✓ Valid Calibre library</span> — ${data.volume_count} volumes found at <code>${escapeHtml(data.path)}</code>`;
    } else {
      statusText.innerHTML = `<span style="color:#f44336;font-weight:600;">✗ Not a valid library</span> — ${escapeHtml(data.error || "unknown error")}`;
    }
  } catch (e) {
    statusText.innerHTML =
      '<span style="color:#f44336;font-weight:600;">✗ Check failed</span> — ' +
      escapeHtml(String(e));
  }
}

/**
 * Import a Calibre library. Kicks off the background import and streams
 * progress from the shared scan-progress SSE endpoint into the progress bar.
 */
async function calibreImport(event) {
  if (event) event.preventDefault();
  const input = document.getElementById("calibre-library-path");
  if (!input || !input.value.trim()) {
    showNotification("Enter a Calibre library path first", "warning");
    return;
  }
  const progressBox = document.getElementById("calibre-import-progress");
  const progressText = document.getElementById("calibre-progress-text");
  const progressBar = document.getElementById("calibre-progress-bar");
  progressBox.style.display = "block";
  progressText.textContent = "Starting import...";
  progressBar.style.width = "0%";

  let scanId = null;
  try {
    const data = await apiPost("/api/library/import-calibre", {
      path: input.value.trim(),
    });
    scanId = data.scan_id;
  } catch (e) {
    progressText.innerHTML = `<span style="color:#f44336;">✗ ${escapeHtml(String(e))}</span>`;
    return;
  }

  // Stream progress via SSE.
  const evtSrc = new EventSource(`/api/library/scan-progress/${scanId}`);
  evtSrc.onmessage = (ev) => {
    let info;
    try {
      info = JSON.parse(ev.data);
    } catch {
      return;
    }
    const phase = info.phase || "";
    const msg = info.message || phase || "Working...";
    const total = info.total_found || 0;
    const processed = info.processed || 0;
    const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
    progressBar.style.width = pct + "%";
    progressText.textContent = `${msg} (${processed}/${total || processed})`;
    if (["completed", "failed", "cancelled"].includes(info.status)) {
      evtSrc.close();
      if (info.status === "completed") {
        progressText.innerHTML = `<span style="color:#4CAF50;font-weight:600;">✓ ${escapeHtml(msg || "Import complete")}</span> — imported ${info.imported || 0}, skipped ${info.skipped || 0}`;
        showNotification("Calibre import complete", "success");
      } else if (info.status === "cancelled") {
        progressText.innerHTML = `<span style="color:#f59e0b;">Cancelled — ${escapeHtml(msg || "")}</span>`;
      } else {
        progressText.innerHTML = `<span style="color:#f44336;">✗ ${escapeHtml(msg || "Import failed")}</span>`;
      }
    }
  };
  evtSrc.onerror = () => {
    evtSrc.close();
  };
}

/**
 * Show notification to user — delegates to the canonical lib/notify.js
 * implementation so settings toasts are theme-aware and screen-reader
 * announced like the library's.
 */
function showNotification(message, type = "info", duration = 5000) {
  // window.notify, not window.showNotification: the declaration above rebinds
  // that global in a classic script, which would recurse into itself.
  return window.notify(message, { type: type || "info", timeoutMs: duration });
}

// Keyboard shortcuts for settings
document.addEventListener("keydown", (e) => {
  // Don't trigger if typing in input fields
  if (
    e.target.tagName === "INPUT" ||
    e.target.tagName === "TEXTAREA" ||
    e.target.tagName === "SELECT"
  ) {
    return;
  }

  // Escape: Return to library
  if (e.key === "Escape") {
    window.location.href = "/";
  }

  // Ctrl/Cmd + S: Save settings
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    saveSettings();
  }
});

// --- Desktop integration: default PDF viewer (spec 014) --------------------
// Applied immediately on toggle (OS-level change), independent of the
// Save button which persists app settings only.

async function loadPdfViewerStatus() {
  const toggle = document.getElementById("pdf-viewer-enabled");
  const statusRow = document.getElementById("pdf-viewer-status-row");
  const statusEl = document.getElementById("pdf-viewer-status");
  if (!toggle) return;
  try {
    const state = await apiGet("/api/settings/pdf-viewer");
    toggle.checked = state.enabled;
    if (state.available) {
      statusEl.textContent = state.enabled
        ? `Registered as the system PDF viewer (previous: ${state.current || "none"})`
        : `Current PDF viewer: ${state.current || "none"}`;
      statusRow.style.display = "";
    }
  } catch (err) {
    toggle.disabled = true;
    console.warn("pdf-viewer status unavailable:", err);
    showNotification(
      `Desktop PDF viewer status unavailable: ${apiErrorMessage(err)}`,
      "warning",
    );
  }
}

async function handlePdfViewerToggle(event) {
  const toggle = event.target;
  const enabled = toggle.checked;
  toggle.disabled = true;
  try {
    await apiPost("/api/settings/pdf-viewer", { enabled });
  } catch (err) {
    toggle.checked = !enabled; // revert on failure
    console.error("pdf-viewer toggle failed:", err);
    showNotification(
      `Could not update the system PDF viewer: ${apiErrorMessage(err)}`,
      "error",
    );
  } finally {
    toggle.disabled = false;
    await loadPdfViewerStatus();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("pdf-viewer-enabled");
  if (toggle) {
    toggle.addEventListener("change", handlePdfViewerToggle);
    loadPdfViewerStatus();
  }
});
