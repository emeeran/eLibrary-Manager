/**
 * Reader: top-bar menus, navigation actions, fullscreen, printing, help modal,
 * and the Escape-to-close behaviour for panels/menus.
 */

/**
 * Toggle layout menu
 */
function toggleLayoutMenu() {
    const menu = document.getElementById('ic-layout-menu');
    hideOtherMenus('ic-layout-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Toggle font size menu
 */
function toggleFontSizeMenu() {
    const menu = document.getElementById('ic-font-size-menu');
    hideOtherMenus('ic-font-size-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';

        const slider = document.getElementById('ic-font-size-slider');
        if (slider) {
            slider.value = IcecreamReader.fontSize;
        }
    }
}

/**
 * Toggle zoom menu
 */
function toggleZoomMenu() {
    const menu = document.getElementById('ic-zoom-menu');
    hideOtherMenus('ic-zoom-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';

        const slider = document.getElementById('ic-zoom-slider');
        if (slider) {
            slider.value = IcecreamReader.zoomLevel;
        }
    }
}

/**
 * Toggle speed menu
 */
function toggleSpeedMenu() {
    const menu = document.getElementById('ic-speed-menu');
    hideOtherMenus('ic-speed-menu');

    if (menu) {
        menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Toggle settings menu
 */
function toggleSettings() {
    toggleSettingsPanel();
}

/**
 * Hide other menus
 */
function hideOtherMenus(exceptId) {
    const menus = ['ic-layout-menu', 'ic-font-size-menu', 'ic-zoom-menu', 'ic-speed-menu', 'ic-settings-menu'];
    menus.forEach(id => {
        if (id !== exceptId) {
            const menu = document.getElementById(id);
            if (menu) menu.style.display = 'none';
        }
    });
}

/**
 * Toggle keyboard shortcuts help modal
 */
function toggleHelpModal() {
    const overlay = document.getElementById('ic-help-overlay');
    if (!overlay) return;
    const isVisible = overlay.style.display !== 'none';
    overlay.style.display = isVisible ? 'none' : 'flex';
}

/**
 * Go to library
 */
function goToLibrary() {
    window.location.href = '/';
}

/**
 * Toggle fullscreen
 */
function toggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen();
    } else {
        document.exitFullscreen();
    }
}

/**
 * Print current chapter
 */
function printChapter() {
    const title = document.getElementById('ic-chapter-title')?.textContent
        || document.getElementById('ic-book-title')?.textContent || 'Chapter';
    let htmlContent = '';

    // In continuous mode, extract only the current chapter's content
    if (IcecreamReader.pageLayout === 'continuous') {
        const contentArea = document.getElementById('ic-chapter-text');
        const dividers = contentArea ? contentArea.querySelectorAll('.ic-chapter-divider') : [];
        let startEl = null;
        let endEl = null;
        dividers.forEach(d => {
            const idx = parseInt(d.dataset.chapterIndex);
            if (idx === IcecreamReader.currentChapter) startEl = d;
            if (idx === IcecreamReader.currentChapter + 1) endEl = d;
        });
        if (startEl) {
            const fragment = document.createElement('div');
            let node = startEl.nextSibling;
            while (node && node !== endEl) {
                fragment.appendChild(node.cloneNode(true));
                node = node.nextSibling;
            }
            htmlContent = fragment.innerHTML;
        }
    }

    // Fallback: print entire content area (single/double page mode)
    if (!htmlContent) {
        const content = document.getElementById('ic-chapter-text');
        if (!content) return;
        htmlContent = content.innerHTML;
    }

    // Create a hidden iframe for printing (avoids popup blocker)
    let iframe = document.getElementById('ic-print-frame');
    if (!iframe) {
        iframe = document.createElement('iframe');
        iframe.id = 'ic-print-frame';
        iframe.style.cssText = 'position:fixed;left:-9999px;width:0;height:0;border:none;';
        document.body.appendChild(iframe);
    }

    const doc = iframe.contentDocument || iframe.contentWindow.document;
    doc.open();
    doc.write(`<!DOCTYPE html><html><head><title>${escapeHtml(title)}</title>
<style>
  @page { margin: 2cm; }
  body { font-family: Georgia, serif; font-size: 11pt; line-height: 1.7; color: #1a1a1a; max-width: 100%; }
  h1 { font-size: 16pt; margin: 0 0 12pt; }
  h2, h3 { margin: 1em 0 0.4em; }
  p { margin: 0 0 0.6em; text-align: justify; }
  img { max-width: 100%; height: auto; }
  .pdf-space { height: 0.6em; }
  table { border-collapse: collapse; width: 100%; margin: 1em 0; }
  th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; font-size: 10pt; }
  th { background: #f0f0f0; font-weight: 600; }
</style></head><body><h1>${escapeHtml(title)}</h1>${htmlContent}</body></html>`);
    doc.close();

    iframe.contentWindow.focus();
    iframe.contentWindow.print();
}

/**
 * Show book info
 */
function showBookInfo() {
    toggleBookInfoPanel();
}

/**
 * Toggle volume
 */
function toggleVolume() {
    toggleVolumeControl();
}

/**
 * Show help
 */
function showHelp() {
    toggleHelpModal();
}

/**
 * Print book
 */
function printBook() {
    window.print();
}
