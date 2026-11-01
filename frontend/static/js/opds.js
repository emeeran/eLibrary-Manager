/**
 * Net Library: OPDS catalog browsing and download (spec 015 v1.1).
 *
 * Frontend for the /api/opds backend (spec 015). All catalog fetches are
 * proxied server-side, so catalog credentials never reach the browser and
 * CORS does not apply. Follows the library.js classic-script conventions:
 * global functions, escapeHtml for any interpolation into innerHTML.
 */

// Opds state: registered catalogs, the catalog being browsed, and the
// current feed URL stack (for future back-navigation).
const Opds = {
  catalogs: [],
  currentCatalogId: null,
  currentCatalogName: "",
};

/**
 * Open the Net Library modal and load the catalog list.
 */
function openNetLibrary() {
  document.getElementById("net-library-modal").classList.remove("hidden");
  showCatalogListView();
}

/**
 * Switch the modal to the catalog-management view.
 */
function showCatalogListView() {
  document.getElementById("net-library-title").textContent = "Net Library";
  document.getElementById("net-library-catalogs-view").style.display = "";
  document.getElementById("net-library-browse-view").style.display = "none";
  loadOpdsCatalogs();
}

/**
 * Fetch and render the registered catalog list.
 */
async function loadOpdsCatalogs() {
  const list = document.getElementById("net-library-catalog-list");
  try {
    const resp = await fetch("/api/opds/catalogs");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    Opds.catalogs = await resp.json();
  } catch {
    list.innerHTML =
      '<div class="opds-empty">Failed to load catalogs. Is the server running?</div>';
    return;
  }

  if (Opds.catalogs.length === 0) {
    list.innerHTML =
      '<div class="opds-empty">No catalogs yet — add one below (e.g. a Calibre-Web OPDS endpoint).</div>';
    return;
  }

  list.innerHTML = Opds.catalogs.map(
    (c) => `
      <div class="opds-catalog-item">
        <div class="opds-catalog-main">
          <div class="opds-catalog-name">${escapeHtml(c.name)}</div>
          <div class="opds-catalog-url">${escapeHtml(c.url)}</div>
          ${c.username ? `<div class="opds-catalog-auth">auth: ${escapeHtml(c.username)}</div>` : ""}
        </div>
        <div class="opds-catalog-actions">
          <button type="button" class="btn btn-primary" onclick="browseOpdsCatalog(${c.id}, '${escapeHtml(c.name)}')">Browse</button>
          <button type="button" class="btn btn-secondary" onclick="deleteOpdsCatalog(${c.id}, '${escapeHtml(c.name)}')">Delete</button>
        </div>
      </div>`,
  );
}

/**
 * Handle the add-catalog form submit.
 * @param {Event} event - Form submit event
 */
async function handleAddCatalog(event) {
  event.preventDefault();
  const payload = {
    name: document.getElementById("opds-name").value.trim(),
    url: document.getElementById("opds-url").value.trim(),
  };
  const username = document.getElementById("opds-username").value.trim();
  const password = document.getElementById("opds-password").value;
  if (username) payload.username = username;
  if (password) payload.password = password;

  try {
    const resp = await fetch("/api/opds/catalogs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      window.notify(body.message || body.detail || "Failed to add catalog", {
        type: "error",
      });
      return;
    }
    window.notify(`Catalog "${payload.name}" added`, { type: "success" });
    document.getElementById("net-library-add-form").reset();
    loadOpdsCatalogs();
  } catch {
    window.notify("Failed to add catalog", { type: "error" });
  }
}

/**
 * Delete a catalog after confirmation.
 * @param {number} catalogId - Catalog id
 * @param {string} name - Catalog display name (for the confirm prompt)
 */
async function deleteOpdsCatalog(catalogId, name) {
  if (!confirm(`Delete catalog "${name}"?`)) return;
  try {
    const resp = await fetch(`/api/opds/catalogs/${catalogId}`, {
      method: "DELETE",
    });
    if (!resp.ok && resp.status !== 204) throw new Error(`HTTP ${resp.status}`);
    window.notify(`Catalog "${name}" deleted`, { type: "success" });
    loadOpdsCatalogs();
  } catch {
    window.notify("Failed to delete catalog", { type: "error" });
  }
}

/**
 * Browse a catalog's root feed.
 * @param {number} catalogId - Catalog id
 * @param {string} name - Catalog display name
 */
async function browseOpdsCatalog(catalogId, name) {
  Opds.currentCatalogId = catalogId;
  Opds.currentCatalogName = name;
  await browseOpdsFeed(null);
}

/**
 * Fetch and render a feed (normalized by the backend proxy).
 * @param {string|null} url - Feed URL; null browses the catalog root
 */
async function browseOpdsFeed(url) {
  document.getElementById("net-library-title").textContent =
    Opds.currentCatalogName || "Net Library";
  document.getElementById("net-library-catalogs-view").style.display = "none";
  document.getElementById("net-library-browse-view").style.display = "";
  document.getElementById("opds-breadcrumb").textContent =
    url ? decodeURIComponent(url.replace(/^[a-z]+:\/\/[^/]+\//, "")) : "Root";

  const list = document.getElementById("opds-entry-list");
  list.innerHTML = '<div class="opds-empty">Loading…</div>';

  const params = url ? `?url=${encodeURIComponent(url)}` : "";
  let feed;
  try {
    const resp = await fetch(
      `/api/opds/catalogs/${Opds.currentCatalogId}/browse${params}`,
    );
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      list.innerHTML = `<div class="opds-empty">${escapeHtml(
        body.message || `Failed to load feed (HTTP ${resp.status})`,
      )}</div>`;
      return;
    }
    feed = body;
  } catch {
    list.innerHTML = '<div class="opds-empty">Network error while loading feed.</div>';
    return;
  }

  if (feed.entries.length === 0) {
    list.innerHTML = '<div class="opds-empty">This feed has no entries.</div>';
    return;
  }

  list.innerHTML = feed.entries
    .map((entry, i) => {
      const nav = entry.is_navigation && entry.download === null;
      const authors = entry.authors && entry.authors.length
        ? `<div class="opds-entry-authors">${escapeHtml(entry.authors.join(", "))}</div>`
        : "";
      const thumb = entry.thumbnail_url
        ? `<img class="opds-entry-thumb" src="${escapeHtml(_thumbUrl(entry.thumbnail_url))}" alt="" loading="lazy">`
        : '<div class="opds-entry-thumb opds-entry-thumb-empty">📖</div>';
      const actions = nav
        ? `<button type="button" class="btn btn-secondary" onclick="openOpdsSection(this)" data-url="${escapeHtml(_navHref(feed, i))}">Open</button>`
        : `<button type="button" class="btn btn-primary" onclick="downloadOpdsEntry(this)" data-url="${escapeHtml(entry.download?.url || "")}" data-title="${escapeHtml(entry.title)}" ${entry.download ? "" : "disabled"}>Download</button>`;
      return `
        <div class="opds-entry">
          ${thumb}
          <div class="opds-entry-main">
            <div class="opds-entry-title">${escapeHtml(entry.title)}${nav ? ' <span class="opds-entry-kind">section</span>' : ""}</div>
            ${authors}
            ${entry.summary ? `<div class="opds-entry-summary">${escapeHtml(entry.summary.slice(0, 180))}</div>` : ""}
          </div>
          <div class="opds-entry-actions">${actions}</div>
        </div>`;
    })
    .join("");
}

/**
 * Resolve a navigation entry's target href (its own link, not a download).
 * The backend marks navigation entries via is_navigation; the href to open
 * is carried on the entry's first subsection link, surfaced here through
 * the data-url attribute set during render.
 * @param {HTMLElement} btn - The clicked "Open" button
 */
async function openOpdsSection(btn) {
  const url = btn.dataset.url;
  if (!url) return;
  await browseOpdsFeed(url);
}

/**
 * Download an acquisition entry into the library.
 * @param {HTMLElement} btn - The clicked Download button (carries data-url
 *   and data-title)
 */
async function downloadOpdsEntry(btn) {
  const url = btn.dataset.url;
  const title = btn.dataset.title || "download";
  if (!url) return;

  // Derive a filename from the title + URL extension (supported formats
  // only — the backend validates the extension).
  const extMatch = url.split("?")[0].match(/\.(epub|pdf|mobi|fb2|cbz|md)$/i);
  const ext = extMatch ? extMatch[1].toLowerCase() : "epub";
  const safeTitle = title.replace(/[^\w\s.-]/g, "").trim().replace(/\s+/g, "_") || "book";
  const filename = `${safeTitle}.${ext}`;

  btn.disabled = true;
  btn.textContent = "Downloading…";
  try {
    const resp = await fetch(`/api/opds/catalogs/${Opds.currentCatalogId}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, filename }),
    });
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      window.notify(body.message || body.detail || "Download failed", {
        type: "error",
      });
      btn.disabled = false;
      btn.textContent = "Download";
      return;
    }
    btn.textContent = "Added ✓";
    window.notify(`"${body.title || title}" added to your library`, {
      type: "success",
    });
    if (typeof loadBooks === "function") loadBooks();
  } catch {
    window.notify("Download failed", { type: "error" });
    btn.disabled = false;
    btn.textContent = "Download";
  }
}

/**
 * Best-effort href for a navigation entry (render-time fallback).
 * @param {object} feed - Normalized feed
 * @param {number} index - Entry index
 * @returns {string} href or empty string
 */
function _navHref(feed, index) {
  return feed.entries[index]?.download?.url || feed.entries[index]?.id || "";
}

/**
 * Thumbnail URL: resolve relative hrefs against the feed URL so the browser
 * can load them when same-origin; absolute URLs load directly.
 * @param {string} thumbnailUrl - Thumbnail href from the feed
 * @returns {string} Resolvable URL or empty string (cross-origin relative
 *   thumbnails are skipped — proxying them is future work)
 */
function _thumbUrl(thumbnailUrl) {
  if (!thumbnailUrl) return "";
  if (/^https?:\/\//i.test(thumbnailUrl)) return thumbnailUrl;
  return "";
}
