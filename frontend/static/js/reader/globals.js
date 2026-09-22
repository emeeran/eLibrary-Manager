/**
 * Reader: global exports.
 *
 * MUST be loaded last. Function declarations above already live on `window`,
 * but we re-export them explicitly to:
 *  - make the public handler surface explicit and grep-able,
 *  - preserve the exact contract the Jinja templates rely on (inline
 *    `onclick="fnName()"` handlers and `window.readerApp.init(bookId)`),
 *  - expose the readerApp controller object used by the template and by
 *    dynamically-generated DOM (e.g. summary tab "generate" buttons).
 */

// Reader controller object — the template calls `window.readerApp.init(bookId)`.
window.readerApp = {
  init: initReader,
  generateSummary,
  generateBookSummary,
  toggleSummary: toggleSummaryPanel,
};

window.setSummaryLength = setSummaryLength;
window.toggleAutoSummary = toggleAutoSummary;
window.copySummary = copySummary;
window.deleteNote = deleteNote;
window.toggleHelpModal = toggleHelpModal;
window.updateScrollProgress = updateScrollProgress;
window.setReaderRating = setReaderRating;
window.uploadReaderCover = uploadReaderCover;

// Public handler surface referenced by inline onclick/onchange/oninput handlers.
window.goToChapter = goToChapter;
window.toggleTOCPanel = toggleTOCPanel;
window.toggleTOCSection = toggleTOCSection;
window.showNotesPanel = showNotesPanel;
window.closeNotesPanel = closeNotesPanel;
window.showBookmarksPanel = showBookmarksPanel;
window.closeBookmarksPanel = closeBookmarksPanel;
window.showSearchPanel = showSearchPanel;
window.closeSearchPanel = closeSearchPanel;
window.toggleSummaryPanel = toggleSummaryPanel;
window.switchSummaryTab = switchSummaryTab;
window.toggleBookInfoPanel = toggleBookInfoPanel;
window.toggleSettingsPanel = toggleSettingsPanel;
window.toggleVolumeControl = toggleVolumeControl;
window.handleSearch = handleSearch;
window.clearSearch = clearSearch;
window.searchNextMatch = searchNextMatch;
window.searchPrevMatch = searchPrevMatch;
window.setTheme = setTheme;
window.setZoom = setZoom;
window.adjustZoom = adjustZoom;
window.setFontSize = setFontSize;
window.setFontFamily = setFontFamily;
window.setLineSpacing = setLineSpacing;
window.setMargin = setMargin;
window.adjustMargin = adjustMargin;
window.setSpeed = setSpeed;
window.setVolume = setVolume;
window.setPageLayout = setPageLayout;
window.toggleTTS = toggleTTS;
window.showHelp = showHelp;
window.printChapter = printChapter;
window.goToLibrary = goToLibrary;
window.toggleFullscreen = toggleFullscreen;
window.openReaderInCalibreWeb = openReaderInCalibreWeb;
window.maybeShowCalibreWebTab = maybeShowCalibreWebTab;
window.applyHighlight = applyHighlight;
window.addSelectionNote = addSelectionNote;
window.copySelection = copySelection;
window.addBookmark = addBookmark;
window.bookmarkSelection = bookmarkSelection;
window.deleteBookmark = deleteBookmark;
window.deleteAnnotation = deleteAnnotation;
window.testAIConnection = testAIConnection;
window.saveAIKey = saveAIKey;
window.saveOllamaUrl = saveOllamaUrl;

// Toggle AI key input based on provider selection
(function () {
  const select = document.getElementById("ic-ai-provider-select");
  const keySection = document.getElementById("ic-ai-key-section");
  const ollamaSection = document.getElementById("ic-ai-ollama-section");
  if (select) {
    select.addEventListener("change", function () {
      const isOllama = this.value === "ollama_local";
      if (keySection) keySection.style.display = isOllama ? "none" : "";
      if (ollamaSection) ollamaSection.style.display = isOllama ? "" : "none";
      // Update placeholder
      const input = document.getElementById("ic-ai-key-input");
      if (input) input.placeholder = isOllama ? "" : "Enter API key...";
    });
    // Initial state
    const isOllama = select.value === "ollama_local";
    if (ollamaSection) ollamaSection.style.display = isOllama ? "" : "none";
  }
})();
