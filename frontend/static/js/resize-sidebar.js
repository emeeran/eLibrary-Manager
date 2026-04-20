/**
 * Shared sidebar resize utility.
 * Makes a sidebar resizable via drag handle.
 * Persists width to localStorage.
 *
 * Usage (left sidebar):  initSidebarResize('sidebar', 'handle', 'key', 200, 150, 500);
 * Usage (right sidebar): initSidebarResize('panel', 'handle', 'key', 260, 180, 500, 'right');
 */
function initSidebarResize(sidebarId, handleId, storageKey, defaultWidth, minWidth, maxWidth, side) {
    var sidebar = document.getElementById(sidebarId);
    var handle = document.getElementById(handleId);
    if (!sidebar || !handle) return;

    var isRight = (side === 'right');

    // Restore saved width
    var saved = localStorage.getItem(storageKey);
    if (saved) {
        var w = Math.max(minWidth, Math.min(maxWidth, parseInt(saved, 10)));
        sidebar.style.width = w + 'px';
        sidebar.style.transition = 'none';
        requestAnimationFrame(function() { sidebar.style.transition = ''; });
    }

    var startX = 0;
    var startWidth = 0;

    function onMouseDown(e) {
        e.preventDefault();
        startX = e.clientX;
        startWidth = sidebar.offsetWidth;
        handle.classList.add('active');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
        sidebar.style.transition = 'none';
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    }

    function onMouseMove(e) {
        var delta = e.clientX - startX;
        // Right sidebar: dragging left increases width (invert delta)
        var newWidth = isRight
            ? Math.max(minWidth, Math.min(maxWidth, startWidth - delta))
            : Math.max(minWidth, Math.min(maxWidth, startWidth + delta));
        sidebar.style.width = newWidth + 'px';
    }

    function onMouseUp() {
        handle.classList.remove('active');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        sidebar.style.transition = '';
        localStorage.setItem(storageKey, sidebar.offsetWidth);
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
    }

    handle.addEventListener('mousedown', onMouseDown);

    // Touch support
    function onTouchStart(e) {
        var touch = e.touches[0];
        startX = touch.clientX;
        startWidth = sidebar.offsetWidth;
        handle.classList.add('active');
        sidebar.style.transition = 'none';
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd);
    }

    function onTouchMove(e) {
        e.preventDefault();
        var touch = e.touches[0];
        var delta = touch.clientX - startX;
        var newWidth = isRight
            ? Math.max(minWidth, Math.min(maxWidth, startWidth - delta))
            : Math.max(minWidth, Math.min(maxWidth, startWidth + delta));
        sidebar.style.width = newWidth + 'px';
    }

    function onTouchEnd() {
        handle.classList.remove('active');
        sidebar.style.transition = '';
        localStorage.setItem(storageKey, sidebar.offsetWidth);
        document.removeEventListener('touchmove', onTouchMove);
        document.removeEventListener('touchend', onTouchEnd);
    }

    handle.addEventListener('touchstart', onTouchStart, { passive: true });
}
