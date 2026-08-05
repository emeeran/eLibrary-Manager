/**
 * Reader: chapter loading, TOC, chapter cache, progress, continuous scroll,
 * and content formatting.
 */

/**
 * Load table of contents with expandable sections
 */
async function loadTableOfContents(bookId) {
  const tocContainer = document.getElementById("ic-toc-content");

  try {
    const response = await fetchRetry(`/api/books/${bookId}/toc`);
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.message || "Failed to load TOC");
    }
    const data = await response.json();

    IcecreamReader.totalChapters = data.total_chapters;
    const totalChaptersEl = document.getElementById("ic-total-pages");
    if (totalChaptersEl) {
      totalChaptersEl.textContent = data.total_chapters;
    }

    if (data.items && data.items.length > 0) {
      IcecreamReader.chapters = data.items;
      renderTableOfContentsWithSections(data.items);
    } else {
      generateChapterList(data.total_chapters);
    }
  } catch (error) {
    console.error("Failed to load TOC:", error);
    generateChapterList(IcecreamReader.totalChapters || 10);
  }
}

/**
 * Render table of contents with expandable sections
 */
function renderTableOfContentsWithSections(items) {
  const tocContainer = document.getElementById("ic-toc-content");
  if (!tocContainer) return;

  let html = "";
  let currentSection = null;

  // Build page-start lookup keyed by actual chapter index
  let pageAccum = 1;
  const pageStartsByChapterIdx = {};
  for (const item of items) {
    const chIdx = item.index;
    if (chIdx !== undefined && !(chIdx in pageStartsByChapterIdx)) {
      pageStartsByChapterIdx[chIdx] = pageAccum;
    }
    pageAccum += IcecreamReader.chapterPageCounts[item.index] || 1;
  }

  items.forEach((item, displayIdx) => {
    const chIdx = item.index !== undefined ? item.index : displayIdx;
    const isActive = chIdx === IcecreamReader.currentChapter;
    const pageLabel = pageStartsByChapterIdx[chIdx]
      ? `p.${pageStartsByChapterIdx[chIdx]}`
      : "";

    // Check if this is a section header (Part, Chapter, etc.)
    if (
      item.level === 1 ||
      (item.title && /^(Part|Chapter|Book|Section)\s/i.test(item.title))
    ) {
      if (currentSection) {
        html += "</div></div>"; // Close previous section
      }

      const sectionId = `section-${displayIdx}`;
      html += `
                <div class="ic-toc-section" id="${sectionId}">
                    <div class="ic-toc-section-header ${isActive ? "active" : ""}" data-index="${chIdx}">
                        <span class="ic-chapter-number">${chIdx + 1}.</span>
                        <span class="ic-toc-section-title" onclick="goToChapter(${chIdx})">${escapeHtml(item.title || `Section ${chIdx + 1}`)}</span>
                        <span class="ic-chapter-page">${pageLabel}</span>
                        <svg class="ic-chevron" width="10" height="10" viewBox="0 0 24 24" fill="currentColor" onclick="toggleTOCSection('${sectionId}')">
                            <path d="M7 10l5 5 5-5z"/>
                        </svg>
                    </div>
                    <div class="ic-toc-section-content">
            `;
      currentSection = sectionId;
    } else {
      // Regular chapter item
      const indent =
        item.level > 1
          ? 'style="padding-left: ' + (16 + item.level * 12) + 'px"'
          : "";
      html += `
                <div class="ic-chapter-item ${isActive ? "active" : ""}"
                     id="toc-item-${chIdx}"
                     data-index="${chIdx}"
                     onclick="goToChapter(${chIdx})"
                     ${indent}>
                    <span class="ic-chapter-number">${chIdx + 1}.</span>
                    <span class="ic-chapter-name">${escapeHtml(item.title || "Chapter " + (chIdx + 1))}</span>
                    <span class="ic-chapter-page">${pageLabel}</span>
                </div>
            `;
    }
  });

  if (currentSection) {
    html += "</div></div>"; // Close last section
  }

  tocContainer.innerHTML = html;
  updateTOCHighlight(IcecreamReader.currentChapter);
}

/**
 * Toggle TOC section expand/collapse
 */
function toggleTOCSection(sectionId) {
  const section = document.getElementById(sectionId);
  if (section) {
    section.classList.toggle("collapsed");
  }
}

/**
 * Efficiently update TOC highlight without re-rendering everything
 */
function updateTOCHighlight(activeIndex) {
  // Clear active from all items
  document
    .querySelectorAll(".ic-chapter-item.active, .ic-toc-section-header.active")
    .forEach((item) => {
      item.classList.remove("active");
    });

  // Highlight by data-index attribute (matches actual chapter index)
  const activeItem = document.querySelector(
    `.ic-chapter-item[data-index="${activeIndex}"]`,
  );
  if (activeItem) {
    activeItem.classList.add("active");
    activeItem.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

  // Try section headers
  const activeHeader = document.querySelector(
    `.ic-toc-section-header[data-index="${activeIndex}"]`,
  );
  if (activeHeader) {
    activeHeader.classList.add("active");
    activeHeader.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // Highlight section header (for items that are section headers with data-index)
  const sectionHeader = document.querySelector(
    `.ic-toc-section-header[data-index="${activeIndex}"]`,
  );
  if (sectionHeader) {
    sectionHeader.classList.add("active");
    // Expand the parent section
    const section = sectionHeader.closest(".ic-toc-section");
    if (section) {
      section.classList.remove("collapsed");
    }
    sectionHeader.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

/**
 * Generate fallback chapter list
 */
function generateChapterList(total) {
  const items = [];
  for (let i = 0; i < total; i++) {
    items.push({ index: i, title: `Chapter ${i + 1}`, level: 1 });
  }
  IcecreamReader.chapters = items;
  renderTableOfContentsWithSections(items);
}

/**
 * Load a specific chapter
 */
async function loadChapter(chapterIndex) {
  if (
    chapterIndex < 0 ||
    (IcecreamReader.totalChapters > 0 &&
      chapterIndex >= IcecreamReader.totalChapters)
  ) {
    return;
  }

  // Reset continuous scroll state when explicitly navigating
  if (IcecreamReader.pageLayout === "continuous") {
    IcecreamReader._continuousRendered = new Set([chapterIndex]);
  }

  if (IcecreamReader.chapterCache.has(chapterIndex)) {
    const cached = IcecreamReader.chapterCache.get(chapterIndex);
    cached.timestamp = Date.now();
    renderChapterData(chapterIndex, cached.data, cached.html, true);
    prefetchAdjacentChapters(chapterIndex);
    return;
  }

  if (IcecreamReader.loading) return;
  IcecreamReader.loading = true;

  const contentArea = document.getElementById("ic-chapter-text");
  contentArea.innerHTML =
    '<div class="ic-loading ic-loading-fast"><div class="ic-spinner"></div></div>';

  try {
    // Rely on the backend's ETag + Cache-Control (1h) for conditional GETs.
    // "no-cache" forces a full revalidation round-trip on every primary
    // load; omitting it lets the browser serve a 304 (or the cached body)
    // when the chapter hasn't changed.
    const response = await fetchRetry(
      `/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`,
    );
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.message || "Failed to load chapter");
    }
    const data = await response.json();

    const formattedHtml = formatChapterContent(data.content);

    IcecreamReader.chapterCache.set(chapterIndex, {
      data: data,
      html: formattedHtml,
      timestamp: Date.now(),
    });

    renderChapterData(chapterIndex, data, formattedHtml);
    prefetchAdjacentChapters(chapterIndex);
  } catch (error) {
    console.error("Failed to load chapter:", error);
    showError("Failed to load chapter. Please try again.");
  } finally {
    IcecreamReader.loading = false;
  }
}

/**
 * Common rendering logic for both fresh and cached loads
 */
function renderChapterData(
  chapterIndex,
  data,
  formattedHtml,
  isCached = false,
) {
  const contentArea = document.getElementById("ic-chapter-text");

  IcecreamReader.currentChapter = chapterIndex;
  if (data.total_chapters) {
    IcecreamReader.totalChapters = data.total_chapters;
  }

  // Track estimated pages per chapter for real page numbers
  if (data.estimated_pages) {
    IcecreamReader.chapterPageCounts[chapterIndex] = data.estimated_pages;
  }

  const totalChaptersEl = document.getElementById("ic-total-pages");
  if (totalChaptersEl) {
    // Calculate total pages from estimated pages, fallback to 1 per chapter
    let total = 0;
    for (let i = 0; i < IcecreamReader.totalChapters; i++) {
      total += IcecreamReader.chapterPageCounts[i] || 1;
    }
    totalChaptersEl.textContent = Math.max(total, IcecreamReader.totalChapters);
  }

  const displayTitle = data.title || "";
  const isGeneric =
    !displayTitle ||
    /^Page \d+$/i.test(displayTitle) ||
    displayTitle === "Untitled Chapter";

  const chapterTitleEl = document.getElementById("ic-chapter-title");
  if (chapterTitleEl) {
    if (!isGeneric) {
      chapterTitleEl.textContent = displayTitle;
      chapterTitleEl.style.display = "block";
    } else {
      chapterTitleEl.style.display = "none";
    }
  }

  // Update footer chapter title
  const footerTitle = document.getElementById("ic-footer-chapter-title");
  if (footerTitle) {
    footerTitle.textContent = isGeneric ? "" : displayTitle;
  }

  contentArea.innerHTML = formattedHtml;

  // Remove duplicate heading from chapter content that matches the UI chapter title
  if (displayTitle && !isGeneric) {
    removeDuplicateHeading(contentArea, displayTitle);
  }

  if (isCached) {
    contentArea.classList.add("ic-cached");
    setTimeout(() => contentArea.classList.remove("ic-cached"), 150);
  } else {
    contentArea.classList.add("ic-loaded");
    setTimeout(() => contentArea.classList.remove("ic-loaded"), 250);
  }

  updateTOCHighlight(chapterIndex);
  updateProgress();
  updateNavButtons();
  saveProgress(chapterIndex);

  // Re-apply persisted highlights from API for this chapter
  loadAnnotations();

  const readingArea = document.getElementById("ic-reading-area");
  if (readingArea) {
    readingArea.scrollTop = 0;
  }

  updateScrollProgress();
}

/**
 * Prefetch adjacent chapters for instant navigation.
 *
 * The NEXT chapter is the most likely navigation target, so it is fetched
 * eagerly (not deferred to idle time) to maximize the cache hit on a forward
 * read. The PREVIOUS chapter is fetched during idle time as a nice-to-have.
 */
function prefetchAdjacentChapters(currentIndex) {
  const nextIndex = currentIndex + 1;
  const prevIndex = currentIndex - 1;

  // Eagerly prefetch the next chapter — forward reading is by far the most
  // common path, and having it warm in the cache makes "next" feel instant.
  if (
    nextIndex < IcecreamReader.totalChapters &&
    !IcecreamReader.chapterCache.has(nextIndex)
  ) {
    prefetchChapter(nextIndex);
  }

  if (prevIndex < 0 || IcecreamReader.chapterCache.has(prevIndex)) return;

  const scheduleWork =
    window.requestIdleCallback || ((cb) => setTimeout(cb, 100));

  scheduleWork(
    () => {
      prefetchChapter(prevIndex);
    },
    { timeout: 2000 },
  );
}

/**
 * Prefetch a single chapter in the background
 */
async function prefetchChapter(chapterIndex) {
  if (
    IcecreamReader.chapterCache.has(chapterIndex) ||
    IcecreamReader.isPrefetching
  ) {
    return;
  }

  IcecreamReader.isPrefetching = true;

  try {
    const response = await fetch(
      `/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`,
    );

    if (response.ok) {
      const data = await response.json();
      const formattedHtml = formatChapterContent(data.content);

      IcecreamReader.chapterCache.set(chapterIndex, {
        data: data,
        html: formattedHtml,
        timestamp: Date.now(),
      });

      evictOldCacheEntries();
    }
  } catch (e) {
    console.warn("[Prefetch] Background fetch failed", e);
  } finally {
    IcecreamReader.isPrefetching = false;
  }
}

/**
 * Evict oldest cache entries when cache exceeds max size
 */
function evictOldCacheEntries() {
  if (IcecreamReader.chapterCache.size <= IcecreamReader.maxCacheSize) {
    return;
  }

  const entries = Array.from(IcecreamReader.chapterCache.entries()).sort(
    (a, b) => a[1].timestamp - b[1].timestamp,
  );

  while (entries.length > IcecreamReader.maxCacheSize) {
    const [key] = entries.shift();
    IcecreamReader.chapterCache.delete(key);
  }
}

/**
 * Remove duplicate heading from chapter content that matches the chapter title.
 * Compares with all whitespace stripped to handle spacing differences.
 */
function removeDuplicateHeading(container, chapterTitle) {
  if (!chapterTitle) return;
  const firstHeading = container.querySelector("h1, h2, h3");
  if (!firstHeading) return;
  const normalize = (str) => str.replace(/\s+/g, "").toLowerCase();
  const headingNorm = normalize(firstHeading.textContent);
  const titleNorm = normalize(chapterTitle);
  if (
    headingNorm === titleNorm ||
    headingNorm.includes(titleNorm) ||
    titleNorm.includes(headingNorm)
  ) {
    firstHeading.remove();
  }
}

/**
 * Format chapter content for display
 */
function formatChapterContent(content) {
  if (!content) return '<p class="empty-content">No content available.</p>';

  content = content.trim();

  if (
    content.startsWith("<") &&
    (content.includes("<p>") ||
      content.includes("<div") ||
      content.includes("pdf-page"))
  ) {
    return content;
  }

  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let currentParagraph = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (!line) {
      if (currentParagraph.length > 0) {
        const text = currentParagraph.join(" ").trim();
        if (text) {
          blocks.push({ type: "paragraph", content: text });
        }
        currentParagraph = [];
      }
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      if (currentParagraph.length > 0) {
        const text = currentParagraph.join(" ").trim();
        if (text) blocks.push({ type: "paragraph", content: text });
        currentParagraph = [];
      }
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        content: headingMatch[2],
      });
      continue;
    }

    currentParagraph.push(line);
  }

  if (currentParagraph.length > 0) {
    const text = currentParagraph.join(" ").trim();
    if (text) blocks.push({ type: "paragraph", content: text });
  }

  return blocks
    .map((block, index) => {
      switch (block.type) {
        case "heading":
          return `<h${block.level}>${formatInlineText(block.content)}</h${block.level}>`;
        case "paragraph":
          return `<p>${formatInlineText(block.content)}</p>`;
        default:
          return "";
      }
    })
    .join("\n");
}

/**
 * Format inline text with bold, italic, links, etc.
 */
function formatInlineText(text) {
  if (!text) return "";

  let result = escapeHtml(text);

  result = result.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  result = result.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  result = result.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
  result = result.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );

  return result;
}

/**
 * Go to specific chapter
 */
function goToChapter(index) {
  if (
    index >= 0 &&
    (IcecreamReader.totalChapters <= 0 || index < IcecreamReader.totalChapters)
  ) {
    loadChapter(index);
  }
}

/**
 * Update reading progress with real page numbers
 */
function updateProgress() {
  const total = IcecreamReader.totalChapters;
  const progress =
    total > 0 ? ((IcecreamReader.currentChapter + 1) / total) * 100 : 0;

  const progressSlider = document.getElementById("ic-progress-slider");
  if (progressSlider) {
    progressSlider.value = progress;
  }

  // Live percentage readout next to the slider.
  const percentEl = document.getElementById("ic-progress-percent");
  if (percentEl) {
    percentEl.textContent =
      (Number.isFinite(progress) ? Math.round(progress) : 0) + "%";
  }

  const pageNumberEl = document.getElementById("ic-page-number");
  const totalPagesEl = document.getElementById("ic-total-pages");

  // Calculate real page numbers from estimated pages per chapter
  // Default to 1 page per chapter (PDFs where chapter = page)
  let currentPage = 1;
  let totalPages = 0;

  for (let i = 0; i < IcecreamReader.totalChapters; i++) {
    const pages = IcecreamReader.chapterPageCounts[i] || 1;
    if (i === IcecreamReader.currentChapter) {
      currentPage = totalPages + 1;
    }
    totalPages += pages;
  }

  if (pageNumberEl) {
    const chapterPages =
      IcecreamReader.chapterPageCounts[IcecreamReader.currentChapter] || 1;
    const endPage = currentPage + chapterPages - 1;
    pageNumberEl.textContent =
      chapterPages > 1 ? `${currentPage}-${endPage}` : `${currentPage}`;
  }

  if (totalPagesEl) {
    totalPagesEl.textContent = totalPages;
  }
}

/**
 * Update prev/next navigation buttons
 */
function updateNavButtons() {
  const prevBtn = document.getElementById("ic-prev-btn");
  const nextBtn = document.getElementById("ic-next-btn");
  const navInfo = document.getElementById("ic-nav-info");

  if (prevBtn) {
    prevBtn.disabled = IcecreamReader.currentChapter <= 0;
  }
  if (nextBtn) {
    nextBtn.disabled =
      IcecreamReader.currentChapter >= IcecreamReader.totalChapters - 1;
  }
  if (navInfo) {
    navInfo.textContent = `${IcecreamReader.currentChapter + 1} / ${IcecreamReader.totalChapters}`;
  }

  // Rich tooltips on the nav buttons: show the title of the chapter they
  // will jump to, so the user knows where they're going before clicking.
  const chapterTitle = (i) => {
    if (i < 0 || i >= IcecreamReader.chapters.length) return "";
    const c = IcecreamReader.chapters[i];
    const t = (c && (c.title || c.name)) || "";
    const isGeneric = !t || /^Page \d+$/i.test(t) || t === "Untitled Chapter";
    return isGeneric ? "" : t;
  };
  if (prevBtn) {
    const pt = chapterTitle(IcecreamReader.currentChapter - 1);
    prevBtn.title = pt ? `Previous: ${pt}` : "Previous chapter";
  }
  if (nextBtn) {
    const nt = chapterTitle(IcecreamReader.currentChapter + 1);
    nextBtn.title = nt ? `Next: ${nt}` : "Next chapter";
  }
}

/**
 * Save reading progress (debounced)
 */
function saveProgress(chapterIndex) {
  if (IcecreamReader.progressSaveTimeout) {
    clearTimeout(IcecreamReader.progressSaveTimeout);
  }

  IcecreamReader.progressSaveTimeout = setTimeout(() => {
    saveProgressNow(chapterIndex);
  }, IcecreamReader.progressSaveDelay);
}

/**
 * Actually save progress to server
 */
async function saveProgressNow(chapterIndex) {
  try {
    const data = JSON.stringify({
      chapter_index: chapterIndex,
      progress: ((chapterIndex + 1) / IcecreamReader.totalChapters) * 100,
    });

    const url = `/api/books/${IcecreamReader.bookId}/progress`;

    if (navigator.sendBeacon) {
      const blob = new Blob([data], { type: "application/json" });
      navigator.sendBeacon(url, blob);
    } else {
      await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: data,
      });
    }
  } catch (error) {
    console.error("Failed to save progress:", error);
  }
}

// Save progress on page unload
window.addEventListener("beforeunload", () => {
  if (IcecreamReader.progressSaveTimeout) {
    clearTimeout(IcecreamReader.progressSaveTimeout);
    saveProgressNow(IcecreamReader.currentChapter);
  }
});

/**
 * Update progress slider tooltip with chapter name
 */
function updateProgressTooltip(slider, tooltip) {
  const progress = parseFloat(slider.value);
  const targetChapter = Math.min(
    Math.floor((progress / 100) * IcecreamReader.totalChapters),
    IcecreamReader.totalChapters - 1,
  );
  const chapterName = IcecreamReader.chapters[targetChapter]
    ? IcecreamReader.chapters[targetChapter].title ||
      `Chapter ${targetChapter + 1}`
    : `Chapter ${targetChapter + 1}`;
  tooltip.textContent = chapterName;

  // Position tooltip near thumb
  const sliderRect = slider.getBoundingClientRect();
  const thumbPosition = (progress / 100) * sliderRect.width;
  tooltip.style.left = thumbPosition + "px";
}

/**
 * Update scroll progress bar within chapter
 */
function updateScrollProgress() {
  const readingArea = document.getElementById("ic-reading-area");
  const progressBar = document.getElementById("ic-scroll-progress-bar");
  if (!readingArea || !progressBar) return;

  const scrollTop = readingArea.scrollTop;
  const scrollHeight = readingArea.scrollHeight - readingArea.clientHeight;
  if (scrollHeight <= 0) {
    progressBar.style.width = "0%";
    return;
  }
  const progress = (scrollTop / scrollHeight) * 100;
  progressBar.style.width = progress + "%";
}

/* Continuous scroll --------------------------------------------------- */

/**
 * Handle continuous scroll (throttled)
 */
let _continuousScrollTimer = null;
function handleContinuousScroll() {
  if (IcecreamReader.pageLayout !== "continuous") return;
  if (_continuousScrollTimer) return; // Throttle: skip if already pending
  _continuousScrollTimer = setTimeout(() => {
    _continuousScrollTimer = null;
  }, 200);

  const readingArea = document.getElementById("ic-reading-area");
  const contentArea = document.getElementById("ic-chapter-text");
  if (!readingArea || !contentArea) return;

  const scrollBottom = readingArea.scrollTop + readingArea.clientHeight;
  const scrollHeight = readingArea.scrollHeight;

  // Load next chapter when near bottom
  if (scrollBottom > scrollHeight - 500) {
    const nextChapter = IcecreamReader.currentChapter + 1;
    if (nextChapter < IcecreamReader.totalChapters) {
      appendChapter(nextChapter); // Don't await — fire and forget
    }
  }

  // Load prev chapter when near top
  if (readingArea.scrollTop < 300) {
    if (IcecreamReader._continuousRendered) {
      const rendered = Array.from(IcecreamReader._continuousRendered).sort(
        (a, b) => a - b,
      );
      const firstRendered = rendered[0];
      if (firstRendered > 0) {
        prependChapter(firstRendered - 1); // Don't await
      }
    }
  }
}

/**
 * Append a chapter to the continuous scroll content
 */
async function appendChapter(chapterIndex) {
  if (!IcecreamReader._continuousRendered)
    IcecreamReader._continuousRendered = new Set();
  if (IcecreamReader._continuousRendered.has(chapterIndex)) return;

  try {
    const response = await fetch(
      `/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`,
    );
    if (!response.ok) return;
    const data = await response.json();
    const formattedHtml = formatChapterContent(data.content);

    // Cache the chapter
    IcecreamReader.chapterCache.set(chapterIndex, {
      data: data,
      html: formattedHtml,
      timestamp: Date.now(),
    });
    if (data.estimated_pages) {
      IcecreamReader.chapterPageCounts[chapterIndex] = data.estimated_pages;
    }

    const contentArea = document.getElementById("ic-chapter-text");
    if (!contentArea) return;

    // Add chapter divider
    const divider = document.createElement("div");
    divider.className = "ic-chapter-divider";
    divider.dataset.chapterIndex = chapterIndex;
    divider.innerHTML = `<h3 class="ic-chapter-divider-title">${escapeHtml(data.title || "Chapter " + (chapterIndex + 1))}</h3>`;
    contentArea.appendChild(divider);

    // Add chapter content
    const chapterDiv = document.createElement("div");
    chapterDiv.className = "ic-continuous-chapter";
    chapterDiv.dataset.chapterIndex = chapterIndex;
    chapterDiv.innerHTML = formattedHtml;
    removeDuplicateHeading(chapterDiv, data.title);
    contentArea.appendChild(chapterDiv);

    IcecreamReader._continuousRendered.add(chapterIndex);
  } catch (e) {
    console.warn("[Continuous] Failed to append chapter", chapterIndex, e);
  }
}

/**
 * Prepend a chapter to the continuous scroll content
 */
async function prependChapter(chapterIndex) {
  if (!IcecreamReader._continuousRendered)
    IcecreamReader._continuousRendered = new Set();
  if (IcecreamReader._continuousRendered.has(chapterIndex)) return;

  try {
    const response = await fetch(
      `/api/books/${IcecreamReader.bookId}/chapter/${chapterIndex}`,
    );
    if (!response.ok) return;
    const data = await response.json();
    const formattedHtml = formatChapterContent(data.content);

    IcecreamReader.chapterCache.set(chapterIndex, {
      data: data,
      html: formattedHtml,
      timestamp: Date.now(),
    });
    if (data.estimated_pages) {
      IcecreamReader.chapterPageCounts[chapterIndex] = data.estimated_pages;
    }

    const contentArea = document.getElementById("ic-chapter-text");
    const readingArea = document.getElementById("ic-reading-area");
    if (!contentArea || !readingArea) return;

    const oldHeight = readingArea.scrollHeight;

    // Add chapter content at the beginning
    const chapterDiv = document.createElement("div");
    chapterDiv.className = "ic-continuous-chapter";
    chapterDiv.dataset.chapterIndex = chapterIndex;
    chapterDiv.innerHTML = formattedHtml;
    removeDuplicateHeading(chapterDiv, data.title);

    const divider = document.createElement("div");
    divider.className = "ic-chapter-divider";
    divider.dataset.chapterIndex = chapterIndex;
    divider.innerHTML = `<h3 class="ic-chapter-divider-title">${escapeHtml(data.title || "Chapter " + (chapterIndex + 1))}</h3>`;

    contentArea.insertBefore(chapterDiv, contentArea.firstChild);
    contentArea.insertBefore(divider, chapterDiv);

    // Preserve scroll position after prepending
    const newHeight = readingArea.scrollHeight;
    readingArea.scrollTop += newHeight - oldHeight;

    IcecreamReader._continuousRendered.add(chapterIndex);
  } catch (e) {
    console.warn("[Continuous] Failed to prepend chapter", chapterIndex, e);
  }
}
