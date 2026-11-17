/**
 * Main Application Orchestrator (DashCode Inspired)
 * Coordinates tabs, mobile navigation, LAN router phone access, notifications, and initialization.
 */
const App = {
  currentTab: "dashboard",
  pollInterval: null,
  lanPhoneUrl: "http://192.168.10.108:8000",

  init() {
    lucide.createIcons();

    // Initialize sub-components
    CrawlerComponent.init();
    GalleryComponent.init();
    AnnotatorComponent.init();
    ReviewComponent.init();
    ConceptStudioComponent.init();

    // Load dynamic LAN router IP info
    this.loadNetworkInfo();

    // Initial stats and polling
    this.refreshDashboardStats();
    this.loadDashboardRecent();
    this.pollInterval = setInterval(() => {
      this.refreshDashboardStats();
      if (this.currentTab === "crawler") CrawlerComponent.refreshStatus();
    }, 3000);

    // Deep-link tab router
    const hash = window.location.hash.replace("#", "");
    if (["dashboard", "crawler", "gallery", "annotate", "review", "concept_studio", "search"].includes(hash)) {
      this.switchTab(hash);
    }
  },

  async loadNetworkInfo() {
    try {
      const net = await API.getNetworkInfo();
      this.lanPhoneUrl = net.phone_url;

      const pillEl = document.getElementById("phone-access-url");
      if (pillEl) pillEl.innerText = net.phone_url.replace("http://", "");

      const qrImg = document.getElementById("qr-code-img");
      if (qrImg) qrImg.src = net.qr_api_url;
    } catch (e) {
      console.error(e);
    }
  },

  copyPhoneUrl() {
    navigator.clipboard.writeText(this.lanPhoneUrl);
    this.toast(`Copied phone URL to clipboard: ${this.lanPhoneUrl}`, "success");
  },

  toggleQrModal() {
    const modal = document.getElementById("qr-modal");
    if (modal) modal.classList.toggle("hidden");
  },

  switchTab(tabName) {
    this.currentTab = tabName;
    window.location.hash = tabName;

    // Toggle view sections
    document.querySelectorAll("section[id^='view-']").forEach((el) => {
      el.classList.add("hidden");
    });
    const target = document.getElementById(`view-${tabName}`);
    if (target) target.classList.remove("hidden");

    // Update desktop sidebar nav styling
    document.querySelectorAll(".nav-tab").forEach((btn) => {
      btn.classList.remove("bg-rose-50", "text-rose-700", "font-bold");
      btn.classList.add("text-slate-600");
    });
    const activeBtn = document.getElementById(`tab-btn-${tabName}`);
    if (activeBtn) {
      activeBtn.classList.add("bg-rose-50", "text-rose-700", "font-bold");
      activeBtn.classList.remove("text-slate-600");
    }

    // Update Top Breadcrumb Title
    const titles = {
      dashboard: "Dashboard Overview",
      crawler: ".np Crawler & Media Ingestion",
      gallery: "Gallery & Filter",
      annotate: "Ground Truth Annotator Workspace",
      review: "Gated AI Approval Queue",
      concept_studio: "AI Concept Studio & iCrawler",
    };
    const titleEl = document.getElementById("top-breadcrumb-title");
    if (titleEl) titleEl.innerText = titles[tabName] || "Platform";

    // Update mobile bottom nav styling (DashCode style)
    document.querySelectorAll(".mobile-nav-btn").forEach((btn) => {
      btn.classList.remove("active");
    });
    const activeMobBtn = document.getElementById(`mob-nav-${tabName}`);
    if (activeMobBtn) {
      activeMobBtn.classList.add("active");
    }

    // Refresh specific view data on tab switch
    if (tabName === "gallery") GalleryComponent.loadPage(GalleryComponent.currentPage);
    if (tabName === "review") ReviewComponent.loadPending();
    if (tabName === "crawler") CrawlerComponent.refreshStatus();
    if (tabName === "dashboard") this.loadDashboardRecent();
    if (tabName === "concept_studio") ConceptStudioComponent.loadSaved();

    // Scroll to top smoothly
    window.scrollTo({ top: 0, behavior: "smooth" });
    lucide.createIcons();
  },

  async refreshDashboardStats() {
    try {
      const stats = await API.getDashboardStats();

      // Top KPI Cards
      const elTotal = document.getElementById("stat-total-imgs");
      const elAppr = document.getElementById("stat-approved-imgs");
      const elAiPen = document.getElementById("stat-ai-pending");
      const elDisk = document.getElementById("free-disk-val");
      const elSbDisk = document.getElementById("sb-free-disk-val");
      const elSbBar = document.getElementById("sb-disk-bar");

      const aiPending = stats.ai_pending_review ?? stats.pending_review ?? 0;

      if (elTotal) elTotal.innerText = stats.total_images.toLocaleString();
      if (elAppr) elAppr.innerText = stats.approved_images.toLocaleString();
      if (elAiPen) elAiPen.innerText = aiPending.toLocaleString();
      if (elDisk) elDisk.innerText = `${stats.disk_free_gb} GB`;
      if (elSbDisk) elSbDisk.innerText = `${stats.disk_free_gb} GB`;

      if (elSbBar) {
        const pctFree = Math.min(100, Math.max(5, (stats.disk_free_gb / 100.0) * 100));
        elSbBar.style.width = `${pctFree}%`;
        elSbBar.className = stats.disk_free_gb < 5 ? "bg-rose-500 h-1.5 rounded-full" : "bg-emerald-500 h-1.5 rounded-full";
      }

      // 50,000 Target Progress
      const target = 50000;
      const pct = Math.min(100, (stats.approved_images / target) * 100);
      const progressBar = document.getElementById("stat-progress-bar");
      const progressPct = document.getElementById("stat-progress-pct");
      if (progressBar) progressBar.style.width = `${Math.max(1, pct)}%`;
      if (progressPct) progressPct.innerText = `${pct.toFixed(2)}%`;

      // AI review badges
      const badgeNav = document.getElementById("ai-pending-badge");
      const badgeSb = document.getElementById("sb-ai-pending-badge");
      const badgeBtn = document.getElementById("btn-review-badge");
      const badgeMob = document.getElementById("mob-badge-review");
      if (badgeNav) {
        badgeNav.innerText = aiPending;
        badgeNav.classList.toggle("hidden", aiPending === 0);
      }
      if (badgeSb) {
        badgeSb.innerText = aiPending;
        badgeSb.classList.toggle("hidden", aiPending === 0);
      }
      if (badgeBtn) badgeBtn.innerText = aiPending;
      if (badgeMob) {
        badgeMob.innerText = aiPending;
        badgeMob.classList.toggle("hidden", aiPending === 0);
      }

      // Media backlog in header
      const topMedia = document.getElementById("top-media-backlog-count");
      if (topMedia && stats.queue_depth !== undefined) {
        topMedia.innerText = stats.queue_depth;
      }
    } catch (err) {
      // quiet
    }
  },

  async loadDashboardRecent() {
    const container = document.getElementById("dash-recent-grid");
    if (!container) return;

    try {
      const data = await API.getImages({ page: 1, limit: 6, sort_by: "newest" });
      container.innerHTML = "";

      if (data.items.length === 0) {
        container.innerHTML = `
          <div class="col-span-full py-8 text-center text-slate-400 text-xs">
            No documents yet. Start crawler to begin acquiring Nepali portals.
          </div>
        `;
        return;
      }

      data.items.forEach(img => {
        const item = document.createElement("div");
        item.className = "bg-white p-2 rounded-xl border border-slate-200 hover:border-rose-300 transition-all cursor-pointer flex flex-col justify-between group shadow-2xs";
        item.onclick = () => {
          AnnotatorComponent.loadImage(img.id);
          App.switchTab("annotate");
        };
        item.innerHTML = `
          <div class="h-28 bg-slate-900 rounded-lg overflow-hidden flex items-center justify-center mb-1.5 relative">
            <img src="/api/images/${img.id}/file" onerror="this.onerror=null; this.src='/static/placeholder.svg'" class="max-h-full max-w-full object-contain">
            <span class="absolute top-1 left-1 px-1.5 py-0.5 rounded text-[9px] font-bold bg-black/70 text-white">#${img.id}</span>
          </div>
          <div class="text-[11px] font-bold text-slate-800 truncate devanagari">
            ${img.caption_nepali || img.ocr_text || `Document #${img.id}`}
          </div>
          <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1 mt-1 border-t border-slate-100">
            <span>${img.width}x${img.height}</span>
            <span class="${img.is_approved ? 'text-emerald-600 font-bold' : 'text-slate-500'}">${img.is_approved ? 'Approved' : 'Ready'}</span>
          </div>
        `;
        container.appendChild(item);
      });
    } catch (e) {
      console.error(e);
    }
  },

  async exportDataset(format = "jsonl") {
    try {
      App.toast(`Exporting approved dataset (${format.toUpperCase()})...`, "info");
      const d = await API.exportDataset(format, true);
      App.toast(`Successfully exported ${d.count} records to ${d.filename}`, "success");
    } catch (err) {
      App.toast(err.message, "error");
    }
  },

  toast(message, type = "info") {
    const toastEl = document.getElementById("toast");
    const msgEl = document.getElementById("toast-msg");
    if (!toastEl || !msgEl) return;

    msgEl.innerText = message;

    const bgMap = {
      success: "bg-emerald-800 text-white border-emerald-600",
      error: "bg-rose-800 text-white border-rose-600",
      warning: "bg-amber-800 text-white border-amber-600",
      info: "bg-slate-900 text-white border-slate-700",
    };

    toastEl.className = `fixed bottom-20 md:bottom-5 right-5 px-4 py-3 rounded-xl shadow-xl text-xs font-semibold flex items-center gap-2.5 border z-50 transform transition-all duration-300 ${bgMap[type] || bgMap.info}`;

    toastEl.classList.remove("translate-y-24", "opacity-0");
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      toastEl.classList.add("translate-y-24", "opacity-0");
    }, 3500);
  },
};

// Start application when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  App.init();
});
