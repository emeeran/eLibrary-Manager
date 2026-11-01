/**
 * Reader: hands-free auto-scroll (spec 002 v1.1 — Moon+ Reader parity).
 *
 * Drives a requestAnimationFrame loop that advances the reading area's
 * scrollTop at the configured speed (px/s). Pauses on direct user scroll
 * input (wheel / touch / pointerdown) and self-stops at the end of the
 * chapter. Speed and persisted state live in settings.js; this module owns
 * only the runtime loop.
 */

// Auto-scroll runtime state (loop-scoped; see toggleAutoScroll).
let _autoScrollRafId = null;
let _autoScrollLastTs = null;
let _autoScrollPaused = false;

/**
 * Whether auto-scroll is currently running (active or paused).
 * @returns {boolean} true if the loop is engaged
 */
function isAutoScrollActive() {
  return _autoScrollRafId !== null;
}

/**
 * Update the toolbar button's visual state.
 * @param {boolean} active - Whether auto-scroll is engaged
 */
function _updateAutoscrollButton(active) {
  const btn = document.getElementById("ic-autoscroll-btn");
  if (btn) btn.classList.toggle("active", active);
}

/**
 * The rAF tick: advance scrollTop by speed * elapsed seconds.
 * @param {number} ts - Timestamp supplied by requestAnimationFrame
 */
function _autoScrollTick(ts) {
  if (_autoScrollLastTs === null) _autoScrollLastTs = ts;
  const dt = (ts - _autoScrollLastTs) / 1000;
  _autoScrollLastTs = ts;

  const area = document.getElementById("ic-reading-area");
  if (!area) {
    toggleAutoScroll(false);
    return;
  }

  if (!_autoScrollPaused) {
    const speed =
      parseInt(localStorage.getItem("reader-autoscroll-speed"), 10) || 0;
    if (speed <= 0) {
      toggleAutoScroll(false);
      return;
    }
    area.scrollTop += speed * dt;

    // Stop at the end of the chapter.
    if (area.scrollTop + area.clientHeight >= area.scrollHeight - 1) {
      toggleAutoScroll(false);
      return;
    }
  }

  _autoScrollRafId = requestAnimationFrame(_autoScrollTick);
}

/**
 * Toggle hands-free auto-scroll.
 *
 * While paused by user interaction, the toggle (with or without `force`)
 * resumes scrolling rather than stopping — only a second explicit toggle on
 * an unpaused session stops it.
 *
 * @param {boolean} [force] - Force a target state; omit to invert current.
 */
function toggleAutoScroll(force) {
  if (isAutoScrollActive() && _autoScrollPaused) {
    // Resume from user-interaction pause.
    resumeAutoScroll();
    _updateAutoscrollButton(true);
    return;
  }

  const enable = force !== undefined ? force : !isAutoScrollActive();

  if (enable && !isAutoScrollActive()) {
    _autoScrollRafId = requestAnimationFrame(_autoScrollTick);
    _autoScrollLastTs = null;
    _autoScrollPaused = false;
    _updateAutoscrollButton(true);
  } else if (!enable && isAutoScrollActive()) {
    cancelAnimationFrame(_autoScrollRafId);
    _autoScrollRafId = null;
    _autoScrollPaused = false;
    _updateAutoscrollButton(false);
  }
}

/**
 * Pause auto-scroll without disengaging (user scrolled manually).
 */
function pauseAutoScroll() {
  if (isAutoScrollActive()) _autoScrollPaused = true;
}

/**
 * Clear the pause flag so the loop resumes advancing.
 */
function resumeAutoScroll() {
  if (isAutoScrollActive()) {
    _autoScrollPaused = false;
    _autoScrollLastTs = null;
  }
}

// Direct scroll input from the reader means "stop driving" — pause the loop
// (it stays engaged so the same key/button resumes). keydown is deliberately
// NOT a pause trigger: the `a` shortcut must not pause itself.
document.addEventListener("wheel", pauseAutoScroll, { passive: true });
document.addEventListener("touchstart", pauseAutoScroll, { passive: true });
document.addEventListener("pointerdown", pauseAutoScroll);
