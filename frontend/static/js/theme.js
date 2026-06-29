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
    // Update the library header toggle icon to match.
    updateThemeToggleIcon(themeName);
}

/** Sun/moon/auto icons for the library theme toggle. */
function updateThemeToggleIcon(themeName) {
    const icon = document.getElementById('theme-toggle-icon');
    if (!icon) return;
    const paths = {
        // day: sun
        day: '<path d="M12 7a5 5 0 100 10 5 5 0 000-10zM12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
        // sepia: sun-horizon
        sepia: '<path d="M12 7a5 5 0 100 10 5 5 0 000-10zM3 18h18M7 13l-2 0M19 13l-2 0M12 4V2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
        // night: crescent moon
        night: '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>',
    };
    icon.innerHTML = paths[themeName] || paths.day;
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.title = `Theme: ${themeName} (click to switch)`;
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
