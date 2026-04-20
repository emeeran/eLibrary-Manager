// Theme Management for eBook Manager

/**
 * Set the application theme.
 * @param {string} themeName - The theme to set ('day', 'sepia', or 'night')
 */
function setTheme(themeName) {
    const validThemes = ['day', 'sepia', 'night'];

    if (!validThemes.includes(themeName)) {
        console.warn(`Invalid theme: ${themeName}. Defaulting to 'day'.`);
        themeName = 'day';
    }

    document.documentElement.setAttribute('data-theme', themeName);
    localStorage.setItem('dawnstar_theme', themeName);

    // Update select if it exists
    const select = document.querySelector('select[onchange*="setTheme"]');
    if (select) {
        select.value = themeName;
    }
}

/**
 * Load saved theme on page load
 */
function loadTheme() {
    const savedTheme = localStorage.getItem('dawnstar_theme') || 'day';
    setTheme(savedTheme);
}

/**
 * Cycle through themes
 */
function cycleTheme() {
    const themes = ['day', 'sepia', 'night'];
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'day';
    const currentIndex = themes.indexOf(currentTheme);
    const nextIndex = (currentIndex + 1) % themes.length;
    setTheme(themes[nextIndex]);
}

// Initialize theme on page load
document.addEventListener('DOMContentLoaded', () => {
    loadTheme();

    // Add keyboard shortcut for theme cycling (Ctrl/Cmd + T)
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 't') {
            e.preventDefault();
            cycleTheme();
        }
    });
});
