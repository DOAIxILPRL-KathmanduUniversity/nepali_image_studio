/**
 * Document Gallery Component (DashCode Edition)
 * High-performance browser with multi-select bulk operations, direct page jumping, and multi-criteria filters.
 */
const GalleryComponent = {
  currentPage: 1,
  limit: 24,
  currentStatusTab: "", // "" (All), "ready", "ai_pending", "approved"
  selectedIds: new Set(),
  currentPageItems: [],

  init() {
    this.bindEvents();
    this.loadPage(1);
  },

  bindEvents() {
    const sortSelect = document.getElementById("gal-sort-by");
    if (sortSelect) {
      sortSelect.addEventListener("change", () => this.loadPage(1));
    }
  },

  setStatusTab(tab) {
    this.currentStatusTab = tab;
    // Update active pill styling
    document.querySelectorAll(".gal-tab-pill").forEach(pill => {
      pill.classList.remove("bg-rose-600", "text-white");
      pill.classList.add("bg-slate-100", "text-slate-600");
    });
    const activePill = document.getElementById(`gal-pill-${tab || 'all'}`);
    if (activePill) {
      activePill.classList.add("bg-rose-600", "text-white");
      activePill.classList.remove("bg-slate-100", "text-slate-600");
    }

    // Toggle Approved Banner
    const appBanner = document.getElementById("gal-approved-banner");
    if (appBanner) {
      appBanner.classList.toggle("hidden", tab !== "approved");
    }

    this.clearSelection();
    this.loadPage(1);
  },

  toggleSelect(id, event) {
    if (event) event.stopPropagation();
    if (this.selectedIds.has(id)) {
      this.selectedIds.delete(id);
    } else {
      this.selectedIds.add(id);
    }
    this.updateBulkBar();

    const chk = document.getElementById(`chk-doc-${id}`);
    if (chk) chk.checked = this.selectedIds.has(id);
  },

  selectAllOnPage() {
    this.currentPageItems.forEach(img => this.selectedIds.add(img.id));
    this.currentPageItems.forEach(img => {
      const chk = document.getElementById(`chk-doc-${img.id}`);
      if (chk) chk.checked = true;
    });
    this.updateBulkBar();
  },

  clearSelection() {
    this.selectedIds.clear();
    document.querySelectorAll(".doc-chk").forEach(c => c.checked = false);
    this.updateBulkBar();
  },

  updateBulkBar() {
    const bar = document.getElementById("gal-bulk-bar");
    const countEl = document.getElementById("gal-bulk-count");
    const count = this.selectedIds.size;
    if (countEl) countEl.innerText = `${count} document${count === 1 ? '' : 's'} selected`;
    if (bar) bar.classList.toggle("hidden", count === 0);
  },

  async bulkApproveSelected() {
    if (this.selectedIds.size === 0) return;
    try {
      const ids = Array.from(this.selectedIds);
      await API.batchImageAction("approve", ids);
      App.toast(`Approved ${ids.length} documents!`, "success");
      this.clearSelection();
      App.refreshDashboardStats();
      this.loadPage(this.currentPage);
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async bulkSetCategoryPrompt() {
    if (this.selectedIds.size === 0) return;
    const cat = prompt("Enter category name for selected documents (e.g. citizenship, lalpurja, gazette, license):");
    if (!cat) return;
    try {
      const ids = Array.from(this.selectedIds);
      await API.batchImageAction("set_category", ids, cat.trim().toLowerCase());
      App.toast(`Assigned category '${cat}' to ${ids.length} documents!`, "success");
      this.clearSelection();
      this.loadPage(this.currentPage);
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  async bulkDiscardSelected() {
    if (this.selectedIds.size === 0) return;
    if (!confirm(`Are you sure you want to permanently delete ${this.selectedIds.size} documents from disk?`)) return;
    try {
      const ids = Array.from(this.selectedIds);
      await API.batchImageAction("discard", ids);
      App.toast(`Deleted ${ids.length} documents from disk`, "warning");
      this.clearSelection();
      App.refreshDashboardStats();
      this.loadPage(this.currentPage);
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  jumpToPage() {
    const inp = document.getElementById("gal-page-jump-inp");
    if (inp) {
      const p = parseInt(inp.value);
      if (p && p >= 1) this.loadPage(p);
    }
  },

  async loadPage(page = 1) {
    this.currentPage = Math.max(1, page);
    const typeFilter = document.getElementById("gal-filter-type")?.value || "";
    const limit = parseInt(document.getElementById("gal-filter-limit")?.value) || 24;
    const search = document.getElementById("gal-search-text")?.value.trim() || "";
    const sortBy = document.getElementById("gal-sort-by")?.value || "newest";

    const params = {
      page: this.currentPage,
      limit,
      document_type: typeFilter,
      search,
      sort_by: sortBy,
    };

    if (this.currentStatusTab === "approved") {
      params.is_approved = true;
    } else if (this.currentStatusTab === "ready") {
      params.status = "ready";
      params.is_approved = false;
    } else if (this.currentStatusTab === "ai_pending") {
      params.annotation_source = "ai_pending";
      params.is_approved = false;
    }

    const grid = document.getElementById("gallery-grid");
    if (!grid) return;

    try {
      const data = await API.getImages(params);
      this.currentPageItems = data.items;
      grid.innerHTML = "";

      if (data.items.length === 0) {
        grid.innerHTML = `
          <div class="col-span-full text-center py-16 text-slate-400 text-xs">
            <i data-lucide="image-off" class="w-10 h-10 mx-auto mb-2 text-slate-300"></i>
            <p class="font-semibold text-slate-600">No documents found matching criteria.</p>
            <p class="text-slate-400 mt-1">Adjust filters or start the crawler to discover more documents.</p>
          </div>
        `;
        lucide.createIcons();
        this.renderPagination(data.page, 1, 0, limit);
        return;
      }

      data.items.forEach(img => {
        const card = document.createElement("div");
        card.className = "bg-white p-2.5 rounded-xl border border-slate-200 shadow-xs hover:shadow-md transition-all cursor-pointer flex flex-col justify-between group doc-card relative";
        
        card.onclick = (e) => {
          if (e.target.closest(".doc-chk-wrap")) return;
          AnnotatorComponent.loadImage(img.id);
          App.switchTab("annotate");
        };

        const isChecked = this.selectedIds.has(img.id);

        const statusBadge = img.is_approved
          ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-100 text-emerald-800">Approved</span>`
          : (img.annotation_source === 'ai_pending'
            ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-100 text-amber-800">AI Pending</span>`
            : `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-slate-100 text-slate-600">Ready</span>`);

        const titleText = img.caption_nepali || img.ocr_text || `Document #${img.id}`;

        card.innerHTML = `
          <div>
            <!-- Select Checkbox -->
            <div class="doc-chk-wrap absolute top-2 right-2 z-10" onclick="event.stopPropagation()">
              <input type="checkbox" id="chk-doc-${img.id}" ${isChecked ? 'checked' : ''} class="doc-chk w-4 h-4 rounded text-rose-600 cursor-pointer" onchange="GalleryComponent.toggleSelect(${img.id}, event)">
            </div>

            <!-- Thumbnail with Contain -->
            <div class="w-full h-36 bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center mb-2 relative">
              <img src="/api/images/${img.id}/file" onerror="this.onerror=null; this.src='/static/placeholder.svg'" class="max-h-full max-w-full object-contain group-hover:scale-105 transition-transform duration-200">
              <span class="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold bg-black/70 text-white">#${img.id}</span>
              ${img.document_type ? `<span class="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded text-[9px] font-semibold bg-indigo-900/80 text-indigo-100 uppercase">${img.document_type}</span>` : ''}
            </div>

            <!-- Title & Snippet Preview -->
            <div class="text-[11px] font-bold text-slate-800 truncate devanagari" title="${titleText}">
              ${titleText}
            </div>
          </div>
          <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1.5 mt-2 border-t border-slate-100">
            <span>${img.width}x${img.height}</span>
            <div>${statusBadge}</div>
          </div>
        `;
        grid.appendChild(card);
      });

      this.renderPagination(data.page, data.total_pages, data.total, limit);
      this.updateBulkBar();
      lucide.createIcons();
    } catch (err) {
      console.error(err);
    }
  },

  renderPagination(current, totalPages, total, limit) {
    const info = document.getElementById("gal-pagination-info");
    const container = document.getElementById("gal-pagination-btns");
    if (!info || !container) return;

    const startIdx = total === 0 ? 0 : (current - 1) * limit + 1;
    const endIdx = Math.min(current * limit, total);
    info.innerText = `Showing ${startIdx} - ${endIdx} of ${total.toLocaleString()} documents`;

    container.innerHTML = "";

    // Prev Button
    const prevBtn = document.createElement("button");
    prevBtn.className = `px-2.5 py-1 rounded border text-xs font-medium ${current > 1 ? 'hover:bg-slate-100 text-slate-700 border-slate-300' : 'text-slate-300 border-slate-200 cursor-not-allowed'}`;
    prevBtn.innerText = "Prev";
    if (current > 1) prevBtn.onclick = () => this.loadPage(current - 1);
    container.appendChild(prevBtn);

    // Numbered Buttons
    const maxBtns = 5;
    let start = Math.max(1, current - 2);
    let end = Math.min(totalPages, start + maxBtns - 1);
    if (end - start < maxBtns - 1) start = Math.max(1, end - maxBtns + 1);

    for (let p = start; p <= end; p++) {
      const btn = document.createElement("button");
      btn.className = `px-2.5 py-1 rounded text-xs font-semibold ${p === current ? 'bg-rose-600 text-white' : 'hover:bg-slate-100 text-slate-700'}`;
      btn.innerText = p;
      btn.onclick = () => this.loadPage(p);
      container.appendChild(btn);
    }

    // Next Button
    const nextBtn = document.createElement("button");
    nextBtn.className = `px-2.5 py-1 rounded border text-xs font-medium ${current < totalPages ? 'hover:bg-slate-100 text-slate-700 border-slate-300' : 'text-slate-300 border-slate-200 cursor-not-allowed'}`;
    nextBtn.innerText = "Next";
    if (current < totalPages) nextBtn.onclick = () => this.loadPage(current + 1);
    container.appendChild(nextBtn);
  },
};
