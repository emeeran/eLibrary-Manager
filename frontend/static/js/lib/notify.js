/* Canonical toast/notification system (loaded as a classic script on every
 * page that shows toasts). One implementation instead of the previous four:
 * accessible (role + aria-live), theme-aware via CSS vars with light
 * fallbacks, capped, auto-dismissing, dismissible.
 *
 * Contract:
 *   notify(message, { type = "info"|"success"|"error"|"warning", timeoutMs, actions })
 *   showNotification(message, type, options)  — legacy signature, delegates
 *   showToast(message, options)               — legacy signature, delegates
 */
(function () {
  "use strict";

  const CONTAINER_ID = "notify-container";
  const VISIBLE_CAP = 3;

  function ensureContainer() {
    let c = document.getElementById(CONTAINER_ID);
    if (!c) {
      c = document.createElement("div");
      c.id = CONTAINER_ID;
      c.setAttribute("role", "region");
      c.setAttribute("aria-label", "Notifications");
      c.style.cssText =
        "position:fixed;bottom:20px;left:50%;transform:translateX(-50%);" +
        "display:flex;flex-direction:column;align-items:center;gap:8px;z-index:10000;" +
        "pointer-events:none;max-width:min(92vw,520px);";
      document.body.appendChild(c);
    }
    return c;
  }

  function colors(type) {
    // Theme-aware via CSS vars where the page defines them; readable fallbacks elsewhere.
    const v = (name, fb) => {
      const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return val || fb;
    };
    const map = {
      success: ["#1b5e20", "#e8f5e9"],
      error: ["#b71c1c", "#fdecea"],
      warning: ["#8d6e00", "#fff8e1"],
      info: [v("--text-primary", "#1e293b"), v("--content-bg-white", "#ffffff")],
    };
    const pair = map[type] || map.info;
    return { fg: pair[0], bg: pair[1] };
  }

  function notify(message, opts) {
    opts = opts || {};
    const type = opts.type || "info";
    const container = ensureContainer();

    while (container.children.length >= VISIBLE_CAP) {
      container.removeChild(container.firstChild);
    }

    const c = colors(type);
    const el = document.createElement("div");
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
    el.style.cssText =
      `pointer-events:auto;display:flex;align-items:center;gap:10px;` +
      `padding:10px 14px;border-radius:10px;box-shadow:0 4px 16px rgba(0,0,0,.18);` +
      `border:1px solid rgba(0,0,0,.08);font-size:14px;line-height:1.4;` +
      `color:${  c.fg  };background:${  c.bg  };`;

    const text = document.createElement("span");
    text.textContent = String(message); // textContent — never innerHTML with caller data
    el.appendChild(text);

    const dismiss = () => {
      if (el.parentNode) el.parentNode.removeChild(el);
      if (opts.onClose) opts.onClose();
    };

    const btn = document.createElement("button");
    btn.type = "button";
    btn.setAttribute("aria-label", "Dismiss notification");
    btn.textContent = "×";
    btn.style.cssText =
      "border:none;background:transparent;color:inherit;font-size:16px;" +
      "cursor:pointer;padding:0 2px;line-height:1;opacity:.7;";
    btn.addEventListener("click", dismiss);
    el.appendChild(btn);

    container.appendChild(el);

    const timeoutMs = opts.timeoutMs != null ? opts.timeoutMs : type === "error" ? 6000 : 3000;
    if (timeoutMs > 0) setTimeout(dismiss, timeoutMs);
    return dismiss;
  }

  // Legacy signatures preserved so existing call sites don't change:
  // library: showNotification(message, type, options) / showError(message)
  // reader:  showToast(message, options?)
  window.notify = notify;
  window.showNotification = function (message, type, options) {
    return notify(message, {
      type: type || "info",
      timeoutMs: options && options.duration != null ? options.duration : undefined,
      onClose: options && options.onClose,
    });
  };
  window.showToast = function (message, options) {
    return notify(message, {
      type: (options && options.type) || "info",
      timeoutMs: options && options.timeout,
    });
  };
})();
